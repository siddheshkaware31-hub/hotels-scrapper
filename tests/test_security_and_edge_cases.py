"""Security and robustness test suite covering SSRF, CSV injection, path traversal, secrets leakage, and concurrency."""

import asyncio
from pathlib import Path

import pytest
from sqlalchemy import func, select

from src.config import Settings
from src.db.repository import HotelRepository
from src.db.session import DatabaseManager
from src.models.entities import Hotel
from src.models.schemas import ExportFormat, HotelData
from src.pipeline.exporter import DataExporter
from src.pipeline.grid import GridQueryGenerator
from src.utils.security import is_safe_maps_url


def test_ssrf_and_url_validation():
    """Verify that only legitimate Google Maps URLs are permitted for browser navigation."""
    # Allowed legitimate URLs
    assert (
        is_safe_maps_url("https://www.google.com/maps/place/Grand+Hotel/@18.9,72.8,17z")
        is True
    )
    assert is_safe_maps_url("https://maps.google.com/maps/search/hotels") is True
    assert is_safe_maps_url("https://maps.app.goo.gl/ABC123XYZ") is True

    # Blocked dangerous / malicious schemes & hosts
    assert is_safe_maps_url("file:///etc/passwd") is False
    assert is_safe_maps_url("file:///C:/Windows/win.ini") is False
    assert is_safe_maps_url("http://169.254.169.254/latest/meta-data/") is False
    assert is_safe_maps_url("http://127.0.0.1:8000/internal-admin") is False
    assert is_safe_maps_url("http://localhost:5000") is False
    assert is_safe_maps_url("javascript:alert(1)") is False
    assert is_safe_maps_url("data:text/html,<script>alert(1)</script>") is False
    assert is_safe_maps_url("https://attacker-controlled-site.com/maps") is False
    assert is_safe_maps_url("https://evilgoogle.com/maps") is False
    assert is_safe_maps_url("") is False
    assert is_safe_maps_url(None) is False


@pytest.mark.asyncio
async def test_csv_formula_injection_mitigation(
    test_db_manager: DatabaseManager, tmp_path: Path
):
    """Verify that leading formula characters (=, +, -, @) are sanitized with single quotes."""
    exporter = DataExporter(test_db_manager, export_dir=str(tmp_path / "exports"))

    async with test_db_manager.session() as session:
        repo = HotelRepository(session)
        # Malicious hotel data designed to trigger formula injection
        exploit_hotel = HotelData(
            place_id="ChI_exploit_1",
            name="=cmd|' /C calc'!A0",
            category="+DkEaL",
            full_address="@SUM(1+1), Mumbai",
            city="Mumbai",
            country="India",
            price_level="-$$$",
            google_maps_url="https://maps.google.com/test",
        )
        await repo.upsert_hotel(exploit_hotel)

    csv_path = await exporter.export_data(fmt=ExportFormat.CSV, city="Mumbai")
    csv_content = csv_path.read_text(encoding="utf-8")

    # Ensure dangerous prefixes are neutralized with leading apostrophe
    assert "'=cmd|' /C calc'!A0" in csv_content
    assert "'+DkEaL" in csv_content
    assert "'@SUM(1+1), Mumbai" in csv_content
    assert "'-$$$" in csv_content


def test_path_traversal_export_protection(
    sample_settings: Settings, test_db_manager: DatabaseManager, tmp_path: Path
):
    """Verify export path traversal attacks and writing to protected OS directories are rejected."""
    exporter = DataExporter(test_db_manager, export_dir=str(tmp_path / "exports"))

    # Traversal to Linux root /etc
    with pytest.raises(PermissionError):
        exporter._resolve_safe_export_path(
            "/etc/cron.d/malicious", ExportFormat.CSV, "test"
        )

    # Traversal to Windows System32
    with pytest.raises(PermissionError):
        exporter._resolve_safe_export_path(
            "C:\\Windows\\System32\\bad.csv", ExportFormat.CSV, "test"
        )

    # Null byte injection
    with pytest.raises(ValueError):
        exporter._resolve_safe_export_path("output.csv\0.exe", ExportFormat.CSV, "test")

    # Extension enforcement
    safe_path = exporter._resolve_safe_export_path(
        str(tmp_path / "custom_output.exe"), ExportFormat.CSV, "test"
    )
    assert safe_path.suffix == ".csv"


def test_grid_infinite_loop_and_bounds_protection():
    """Verify GridQueryGenerator is immune to infinite loops, zero steps, and inverted coordinates."""
    # Zero or negative step size must not hang
    cells_zero = GridQueryGenerator.generate_grid_cells(
        18.9, 19.2, 72.8, 73.0, step_km=0.0
    )
    assert len(cells_zero) > 0

    cells_neg = GridQueryGenerator.generate_grid_cells(
        18.9, 19.2, 72.8, 73.0, step_km=-10.0
    )
    assert len(cells_neg) > 0

    # Inverted bounding box (min > max) must be auto-corrected
    cells_inverted = GridQueryGenerator.generate_grid_cells(
        19.2, 18.9, 73.0, 72.8, step_km=5.0
    )
    assert len(cells_inverted) > 0

    # Extremely small bounding box must return at least 1 center cell
    cells_tiny = GridQueryGenerator.generate_grid_cells(
        18.9001, 18.9002, 72.8001, 72.8002, step_km=5.0
    )
    assert len(cells_tiny) == 1


@pytest.mark.asyncio
async def test_sql_like_wildcard_escaping(test_db_manager: DatabaseManager):
    """Verify SQL ILIKE search escapes wildcard characters % and _ properly."""
    async with test_db_manager.session() as session:
        repo = HotelRepository(session)
        # Hotel in city with literal percent symbol
        h1 = HotelData(
            place_id="p_percent",
            name="Percent Hotel",
            city="100% City",
            google_maps_url="https://maps.google.com/test",
        )
        h2 = HotelData(
            place_id="p_other",
            name="Other Hotel",
            city="1000 Other City",
            google_maps_url="https://maps.google.com/test2",
        )
        await repo.upsert_hotel(h1)
        await repo.upsert_hotel(h2)

    async with test_db_manager.session() as session:
        repo = HotelRepository(session)
        # Search specifically for "100%"
        results = await repo.get_hotels_for_export(city="100%")
        # Should only match "100% City", not "1000 Other City"
        assert len(results) == 1
        assert results[0].place_id == "p_percent"


@pytest.mark.asyncio
async def test_sqlite_concurrent_write_stress(test_db_manager: DatabaseManager):
    """Stress test SQLite write locks under high concurrent task load."""

    async def worker(index: int):
        async with test_db_manager.session() as session:
            repo = HotelRepository(session)
            hotel = HotelData(
                place_id=f"stress_hotel_{index}",
                name=f"Stress Hotel {index}",
                rating=4.0 + (index % 10) * 0.1,
                google_maps_url=f"https://maps.google.com/stress_{index}",
            )
            await repo.upsert_hotel(hotel)

    # Dispatch 25 concurrent write operations simultaneously
    tasks = [worker(i) for i in range(25)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Ensure none raised OperationalError: database is locked
    for res in results:
        assert not isinstance(res, Exception), (
            f"Concurrent write failed with exception: {res}"
        )

    async with test_db_manager.session() as session:
        total = (await session.execute(select(func.count(Hotel.place_id)))).scalar()
        assert total == 25
