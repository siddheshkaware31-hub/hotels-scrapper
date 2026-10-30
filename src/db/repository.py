"""Data access repository for hotels, job execution states, and task queues."""

from collections.abc import Sequence
from datetime import UTC, datetime

import structlog
from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.entities import Hotel, JobRun, ScrapingTask
from src.models.schemas import HotelCandidate, HotelData, JobStatus, TaskStatus

logger = structlog.get_logger(__name__)


class HotelRepository:
    """Async repository encapsulating DB operations with idempotency and upsert semantics."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def upsert_hotel(self, data: HotelData) -> Hotel:
        """Upsert hotel by place_id. Updates existing attributes or inserts a new row."""
        stmt = select(Hotel).where(Hotel.place_id == data.place_id)
        result = await self.session.execute(stmt)
        existing: Hotel | None = result.scalar_one_or_none()

        now = datetime.now(UTC)
        if existing:
            existing.name = data.name
            existing.category = data.category
            existing.source = data.source
            existing.price = data.price or existing.price
            existing.source_url = data.source_url or existing.source_url
            existing.full_address = data.full_address
            existing.city = data.city or existing.city
            existing.country = data.country or existing.country
            existing.latitude = data.latitude
            existing.longitude = data.longitude
            existing.phone = data.phone
            existing.website = data.website
            existing.rating = data.rating
            existing.review_count = data.review_count
            existing.price_level = data.price_level
            existing.check_in_info = data.check_in_info
            existing.amenities = data.amenities
            existing.photo_urls = data.photo_urls
            existing.google_maps_url = data.google_maps_url
            existing.scraped_at = data.scraped_at
            existing.updated_at = now
            logger.info("hotel_upserted", place_id=data.place_id, action="updated")
            return existing
        else:
            new_hotel = Hotel(
                place_id=data.place_id,
                name=data.name,
                category=data.category,
                source=data.source,
                price=data.price,
                source_url=data.source_url,
                full_address=data.full_address,
                city=data.city,
                country=data.country,
                latitude=data.latitude,
                longitude=data.longitude,
                phone=data.phone,
                website=data.website,
                rating=data.rating,
                review_count=data.review_count,
                price_level=data.price_level,
                check_in_info=data.check_in_info,
                amenities=data.amenities,
                photo_urls=data.photo_urls,
                google_maps_url=data.google_maps_url,
                scraped_at=data.scraped_at,
                created_at=now,
                updated_at=now,
            )
            self.session.add(new_hotel)
            logger.info("hotel_upserted", place_id=data.place_id, action="inserted")
            return new_hotel

    async def create_job_run(self, job_id: str, region: str) -> JobRun:
        """Create a new job run entry."""
        job = JobRun(
            id=job_id,
            region=region,
            status=JobStatus.RUNNING.value,
            total_candidates=0,
            completed_count=0,
            failed_count=0,
            started_at=datetime.now(UTC),
        )
        self.session.add(job)
        return job

    async def get_job_run(self, job_id: str) -> JobRun | None:
        stmt = select(JobRun).where(JobRun.id == job_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_resumable_job(
        self, region: str | None = None
    ) -> JobRun | None:
        """Find the latest unfinished or paused job run."""
        stmt = (
            select(JobRun)
            .where(JobRun.status.in_([JobStatus.RUNNING.value, JobStatus.PAUSED.value]))
            .order_by(desc(JobRun.started_at))
        )
        if region:
            stmt = stmt.where(JobRun.region == region)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def add_candidates(
        self, job_id: str, candidates: list[HotelCandidate]
    ) -> int:
        """Enqueue candidates as tasks with batched deduplication to avoid N+1 query overhead."""
        if not candidates:
            return 0

        # Batch query existing tasks in a single query
        stmt = select(ScrapingTask.google_maps_url, ScrapingTask.place_id).where(
            ScrapingTask.job_run_id == job_id
        )
        existing_rows = (await self.session.execute(stmt)).all()
        existing_urls = {row[0] for row in existing_rows if row[0]}
        existing_pids = {row[1] for row in existing_rows if row[1]}

        added_count = 0
        seen_in_batch = set()

        for cand in candidates:
            if (
                not cand.google_maps_url
                or cand.google_maps_url in existing_urls
                or cand.google_maps_url in seen_in_batch
            ):
                continue
            if cand.place_id and cand.place_id in existing_pids:
                continue

            task = ScrapingTask(
                job_run_id=job_id,
                place_id=cand.place_id,
                google_maps_url=cand.google_maps_url,
                area_query=cand.area_query,
                status=TaskStatus.PENDING.value,
                retry_count=0,
            )
            self.session.add(task)
            seen_in_batch.add(cand.google_maps_url)
            if cand.place_id:
                existing_pids.add(cand.place_id)
            added_count += 1

        if added_count > 0:
            await self.session.execute(
                update(JobRun)
                .where(JobRun.id == job_id)
                .values(total_candidates=JobRun.total_candidates + added_count)
            )
        return added_count

    async def get_pending_tasks(
        self,
        job_id: str,
        max_retries: int = 3,
        limit: int | None = None,
    ) -> Sequence[ScrapingTask]:
        """Fetch pending tasks or tasks eligible for retry with optional pagination limit."""
        stmt = (
            select(ScrapingTask)
            .where(
                (ScrapingTask.job_run_id == job_id)
                & (
                    (ScrapingTask.status == TaskStatus.PENDING.value)
                    | (
                        (ScrapingTask.status == TaskStatus.FAILED.value)
                        & (ScrapingTask.retry_count < max_retries)
                    )
                )
            )
            .order_by(ScrapingTask.id.asc())
        )
        if limit:
            stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def update_task_progress(
        self,
        task_id: int,
        status: TaskStatus,
        place_id: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Update individual task status and synchronize job counters."""
        task_stmt = select(ScrapingTask).where(ScrapingTask.id == task_id)
        task = (await self.session.execute(task_stmt)).scalar_one_or_none()
        if not task:
            return

        task.status = status.value
        if place_id:
            task.place_id = place_id
        if error_message:
            task.error_message = error_message
            task.retry_count += 1

        task.updated_at = datetime.now(UTC)

        # Update job stats
        job_stmt = select(JobRun).where(JobRun.id == task.job_run_id)
        job = (await self.session.execute(job_stmt)).scalar_one_or_none()
        if job:
            if status == TaskStatus.COMPLETED:
                job.completed_count += 1
            elif status == TaskStatus.FAILED:
                job.failed_count += 1

    async def finish_job_run(
        self, job_id: str, status: JobStatus, error_message: str | None = None
    ) -> None:
        """Mark job run as completed or failed."""
        stmt = (
            update(JobRun)
            .where(JobRun.id == job_id)
            .values(
                status=status.value,
                finished_at=datetime.now(UTC),
                error_message=error_message,
            )
        )
        await self.session.execute(stmt)

    async def get_hotels_for_export(self, city: str | None = None) -> Sequence[Hotel]:
        """Fetch all hotels or hotels filtered by city with wildcard escaping."""
        stmt = select(Hotel).order_by(Hotel.name.asc())
        if city:
            # Escape SQL LIKE wildcards (% and _) and escape character
            escaped_city = (
                city.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            )
            stmt = stmt.where(Hotel.city.ilike(f"%{escaped_city}%", escape="\\"))
        result = await self.session.execute(stmt)
        return result.scalars().all()
