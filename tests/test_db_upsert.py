"""Unit tests for database deduplication, upsert logic, and resume state."""

import pytest
from sqlalchemy import func, select

from src.db.repository import HotelRepository
from src.models.entities import Hotel
from src.models.schemas import HotelCandidate, HotelData, TaskStatus


@pytest.mark.asyncio
async def test_upsert_hotel_inserts_and_updates(test_session):
    repo = HotelRepository(test_session)

    hotel1 = HotelData(
        place_id="ChI_test_hotel_1",
        name="Test Hotel Deluxe",
        category="Hotel",
        full_address="123 Ocean Drive, Mumbai",
        city="Mumbai",
        country="India",
        rating=4.5,
        review_count=100,
        google_maps_url="https://maps.google.com/test1",
    )

    # First insert
    await repo.upsert_hotel(hotel1)
    await test_session.commit()

    count = (await test_session.execute(select(func.count(Hotel.place_id)))).scalar()
    assert count == 1

    # Second upsert with updated rating and reviews
    hotel1_updated = HotelData(
        place_id="ChI_test_hotel_1",
        name="Test Hotel Deluxe (Renovated)",
        category="Luxury Hotel",
        full_address="123 Ocean Drive, Mumbai",
        city="Mumbai",
        country="India",
        rating=4.8,
        review_count=150,
        google_maps_url="https://maps.google.com/test1",
    )

    await repo.upsert_hotel(hotel1_updated)
    await test_session.commit()

    # Verify no duplicate was inserted
    count_after = (
        await test_session.execute(select(func.count(Hotel.place_id)))
    ).scalar()
    assert count_after == 1

    # Verify attributes updated
    saved = (
        await test_session.execute(
            select(Hotel).where(Hotel.place_id == "ChI_test_hotel_1")
        )
    ).scalar_one()
    assert saved.name == "Test Hotel Deluxe (Renovated)"
    assert saved.rating == 4.8
    assert saved.review_count == 150
    assert saved.category == "Luxury Hotel"


@pytest.mark.asyncio
async def test_job_and_task_resume_tracking(test_session):
    repo = HotelRepository(test_session)
    job_id = "test_job_101"

    # Create job run
    job = await repo.create_job_run(job_id, "Mumbai")
    await test_session.commit()

    # Add candidates
    candidates = [
        HotelCandidate(
            google_maps_url="https://maps.google.com/h1",
            area_query="Colaba",
            place_id="p1",
        ),
        HotelCandidate(
            google_maps_url="https://maps.google.com/h2",
            area_query="Bandra",
            place_id="p2",
        ),
    ]
    added = await repo.add_candidates(job_id, candidates)
    await test_session.commit()
    assert added == 2

    # Verify tasks are pending
    tasks = await repo.get_pending_tasks(job_id)
    assert len(tasks) == 2

    # Complete one task
    await repo.update_task_progress(tasks[0].id, TaskStatus.COMPLETED, place_id="p1")
    await test_session.commit()

    # Verify only 1 pending task remains
    pending_tasks = await repo.get_pending_tasks(job_id)
    assert len(pending_tasks) == 1
    assert pending_tasks[0].place_id == "p2"

    # Check resume retrieval
    resumable_job = await repo.get_latest_resumable_job(region="Mumbai")
    assert resumable_job is not None
    assert resumable_job.id == job_id
