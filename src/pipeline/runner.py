"""Pipeline orchestrator handling task dispatching, concurrency, retries, and resume semantics."""

import asyncio
import uuid

import structlog

from src.config import RegionConfig, Settings
from src.db.repository import HotelRepository
from src.db.session import DatabaseManager
from src.models.entities import ScrapingTask
from src.models.schemas import HotelCandidate, JobStatus, TaskStatus
from src.pipeline.grid import GridQueryGenerator
from src.providers import get_provider
from src.providers.base import BaseHotelProvider
from src.providers.google_maps.anti_detect import CaptchaDetectedException
from src.utils.backoff import calculate_jittered_backoff, polite_sleep

logger = structlog.get_logger(__name__)


class PipelineOrchestrator:
    """Coordinates search discovery, queue persistence, concurrent worker extraction, and job resumption."""

    def __init__(
        self,
        settings: Settings,
        db_manager: DatabaseManager,
        provider: BaseHotelProvider | None = None,
    ):
        self.settings = settings
        self.db_manager = db_manager
        self.provider = provider or get_provider(settings)
        self._captcha_event = asyncio.Event()
        self._captcha_event.set()  # Set means clear to run; cleared means paused

    def _find_region_config(self, region_name: str) -> RegionConfig | None:
        """Find matching region definition in settings."""
        for r in self.settings.regions:
            if r.name.lower() == region_name.lower():
                return r
        return None

    async def execute_scrape(
        self,
        region_name: str,
        resume_job_id: str | None = None,
    ) -> str:
        """Run the end-to-end extraction pipeline for a given region."""
        region_cfg = self._find_region_config(region_name)
        if not region_cfg and not resume_job_id:
            # Dynamically construct fallback single-query region config
            region_cfg = RegionConfig(
                name=region_name,
                country="",
                query_template="hotels in {area}",
                strategy="neighborhoods",
                neighborhoods=[region_name],
            )

        job_id = resume_job_id or f"job_{region_name.lower()}_{uuid.uuid4().hex[:8]}"

        await self.db_manager.create_tables()
        await self.provider.initialize()

        try:
            async with self.db_manager.session() as session:
                repo = HotelRepository(session)
                existing_job = await repo.get_job_run(job_id)
                if not existing_job:
                    await repo.create_job_run(job_id, region_name)
                    logger.info(
                        "new_job_run_created", job_id=job_id, region=region_name
                    )
                else:
                    logger.info(
                        "resuming_existing_job_run", job_id=job_id, region=region_name
                    )

            # Phase 1: Search Discovery (skip if resuming and tasks already exist)
            async with self.db_manager.session() as session:
                repo = HotelRepository(session)
                pending_count = len(
                    await repo.get_pending_tasks(
                        job_id, max_retries=self.settings.scraper.anti_bot.max_retries
                    )
                )

            if pending_count == 0 and region_cfg:
                targets = GridQueryGenerator.generate_targets_for_region(region_cfg)
                logger.info(
                    "initiating_search_discovery_phase", total_targets=len(targets)
                )

                for target in targets:
                    try:
                        candidates = await self.provider.search_candidates(target)
                        async with self.db_manager.session() as session:
                            repo = HotelRepository(session)
                            added = await repo.add_candidates(job_id, candidates)
                            logger.info(
                                "candidates_enqueued",
                                target=target.query_text,
                                discovered=len(candidates),
                                newly_added=added,
                            )
                    except CaptchaDetectedException:
                        logger.critical(
                            "captcha_encountered_during_search_phase_pausing"
                        )
                        await self._handle_captcha_cooldown()
                    except Exception as e:
                        logger.error(
                            "search_target_failed",
                            target=target.query_text,
                            error=str(e),
                        )

            # Phase 2: Detail Extraction Worker Pool
            await self._run_worker_pool(job_id, region_cfg)

            # Finalize Job State
            async with self.db_manager.session() as session:
                repo = HotelRepository(session)
                remaining = await repo.get_pending_tasks(
                    job_id, max_retries=self.settings.scraper.anti_bot.max_retries
                )
                status = (
                    JobStatus.COMPLETED if len(remaining) == 0 else JobStatus.PAUSED
                )
                await repo.finish_job_run(job_id, status=status)
                logger.info("job_run_finished", job_id=job_id, status=status.value)

            return job_id

        finally:
            await self.provider.close()

    async def _handle_captcha_cooldown(self) -> None:
        """Pause worker tasks and back off when CAPTCHA is detected."""
        self._captcha_event.clear()
        cooldown = self.settings.scraper.anti_bot.captcha_cooldown_sec
        logger.warning(
            "anti_bot_alert_captcha_cooldown_initiated",
            cooldown_seconds=cooldown,
            message="Google presented bot detection. Sleeping to allow IP cooldown without solving.",
        )
        await asyncio.sleep(cooldown)
        self._captcha_event.set()
        logger.info("anti_bot_cooldown_completed_resuming_workers")

    async def _run_worker_pool(
        self, job_id: str, region_cfg: RegionConfig | None
    ) -> None:
        """Dispatch detail extraction tasks bounded by concurrency semaphore."""
        semaphore = asyncio.Semaphore(self.settings.scraper.concurrency)

        async def worker_task(task_entity: ScrapingTask):
            async with semaphore:
                # Wait if CAPTCHA cooldown is active
                await self._captcha_event.wait()

                city_hint = region_cfg.name if region_cfg else None
                country_hint = region_cfg.country if region_cfg else None

                candidate = HotelCandidate(
                    google_maps_url=task_entity.google_maps_url,
                    area_query=task_entity.area_query,
                    place_id=task_entity.place_id,
                )

                max_retries = self.settings.scraper.anti_bot.max_retries
                for attempt in range(task_entity.retry_count, max_retries + 1):
                    try:
                        hotel = await self.provider.get_hotel_details(
                            candidate=candidate,
                            city_context=city_hint,
                            country_context=country_hint,
                        )

                        # Upsert hotel and mark task completed
                        async with self.db_manager.session() as session:
                            repo = HotelRepository(session)
                            await repo.upsert_hotel(hotel)
                            await repo.update_task_progress(
                                task_id=task_entity.id,
                                status=TaskStatus.COMPLETED,
                                place_id=hotel.place_id,
                            )

                        # Politeness delay between item visits
                        await polite_sleep(
                            self.settings.scraper.min_delay_sec,
                            self.settings.scraper.max_delay_sec,
                        )
                        return

                    except CaptchaDetectedException:
                        logger.critical(
                            "captcha_encountered_during_detail_worker",
                            task_id=task_entity.id,
                        )
                        await self._handle_captcha_cooldown()

                    except Exception as exc:
                        logger.warning(
                            "detail_extraction_attempt_failed",
                            task_id=task_entity.id,
                            attempt=attempt,
                            error=str(exc),
                        )
                        if attempt < max_retries:
                            backoff = calculate_jittered_backoff(attempt)
                            logger.info(
                                "applying_jittered_backoff",
                                seconds=backoff,
                                task_id=task_entity.id,
                            )
                            await asyncio.sleep(backoff)
                        else:
                            # Retries exhausted
                            async with self.db_manager.session() as session:
                                repo = HotelRepository(session)
                                await repo.update_task_progress(
                                    task_id=task_entity.id,
                                    status=TaskStatus.FAILED,
                                    error_message=str(exc),
                                )

        batch_size = 50
        prev_pending_count = -1
        while True:
            async with self.db_manager.session() as session:
                repo = HotelRepository(session)
                tasks = await repo.get_pending_tasks(
                    job_id,
                    max_retries=self.settings.scraper.anti_bot.max_retries,
                    limit=batch_size,
                )

            if not tasks:
                break

            current_pending_count = len(tasks)
            logger.info("processing_batch_of_tasks", batch_size=current_pending_count)
            # Run tasks concurrently up to concurrency limit
            await asyncio.gather(
                *(worker_task(t) for t in tasks), return_exceptions=True
            )

            if current_pending_count == prev_pending_count:
                async with self.db_manager.session() as session:
                    repo = HotelRepository(session)
                    remaining = await repo.get_pending_tasks(
                        job_id,
                        max_retries=self.settings.scraper.anti_bot.max_retries,
                        limit=batch_size,
                    )
                if len(remaining) >= current_pending_count:
                    logger.warning("no_progress_made_in_batch_halting_loop")
                    break
            prev_pending_count = current_pending_count
