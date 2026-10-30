"""Shared pytest async fixtures and test infrastructure."""

from pathlib import Path

import pytest
import pytest_asyncio

from src.config import (
    AppConfig,
    BoundingBoxConfig,
    RegionConfig,
    ScraperConfig,
    Settings,
)
from src.db.session import DatabaseManager


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures" / "html"


@pytest.fixture
def sample_settings(tmp_path: Path) -> Settings:
    """Provide isolated settings pointing to temporary directories."""
    return Settings(
        app=AppConfig(
            data_dir=str(tmp_path / "data"),
            snapshots_dir=str(tmp_path / "snapshots"),
            export_dir=str(tmp_path / "exports"),
        ),
        scraper=ScraperConfig(
            concurrency=2,
            headless=True,
            user_data_dir=str(tmp_path / "browser_ctx"),
        ),
        regions=[
            RegionConfig(
                name="Mumbai",
                country="India",
                strategy="grid",
                bbox=BoundingBoxConfig(
                    min_lat=18.90,
                    max_lat=19.20,
                    min_lng=72.80,
                    max_lng=72.95,
                ),
                grid_step_km=5.0,
                neighborhoods=["Colaba", "Bandra"],
            )
        ],
    )


@pytest_asyncio.fixture
async def test_db_manager():
    """In-memory async SQLite database manager for fast, isolated tests."""
    mgr = DatabaseManager("sqlite+aiosqlite:///:memory:", echo=False)
    mgr.initialize()
    await mgr.create_tables()
    yield mgr
    await mgr.close()


@pytest_asyncio.fixture
async def test_session(test_db_manager: DatabaseManager):
    """Yield an isolated async database session."""
    async with test_db_manager.session() as session:
        yield session
