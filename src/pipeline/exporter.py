"""Database export service supporting CSV and JSON serialization."""

import csv
import json
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import structlog

from src.db.repository import HotelRepository
from src.db.session import DatabaseManager
from src.models.entities import Hotel
from src.models.schemas import ExportFormat

logger = structlog.get_logger(__name__)


class DataExporter:
    """Exports hotel database records into CSV or JSON files."""

    def __init__(self, db_manager: DatabaseManager, export_dir: str = "data/exports"):
        self.db_manager = db_manager
        self.export_dir = Path(export_dir)
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def _hotel_to_dict(self, h: Hotel) -> dict:
        """Serialize ORM Hotel instance into a clean dictionary."""
        return {
            "place_id": h.place_id,
            "name": h.name,
            "source": getattr(h, "source", "Google Maps"),
            "price": getattr(h, "price", None),
            "category": h.category,
            "full_address": h.full_address,
            "city": h.city,
            "country": h.country,
            "latitude": h.latitude,
            "longitude": h.longitude,
            "phone": h.phone,
            "website": h.website,
            "rating": h.rating,
            "review_count": h.review_count,
            "price_level": h.price_level,
            "check_in_info": h.check_in_info,
            "amenities": h.amenities or [],
            "photo_urls": h.photo_urls or [],
            "source_url": getattr(h, "source_url", None) or h.google_maps_url,
            "google_maps_url": h.google_maps_url,
            "scraped_at": h.scraped_at.isoformat() if h.scraped_at else None,
        }

    def _sanitize_csv_cell(self, value: object) -> str:
        """Mitigate CSV Formula Injection (CWE-1236) by quoting risky leading formula triggers."""
        if value is None:
            return ""
        s = str(value)
        # Leading trigger characters in spreadsheets that execute formulas
        if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
            return f"'{s}"
        return s

    def _resolve_safe_export_path(
        self, output_file: str | None, fmt: ExportFormat, default_filename: str
    ) -> Path:
        """Resolve destination path, preventing path traversal and enforcing extension safety."""
        if not output_file:
            return self.export_dir / f"{default_filename}.{fmt.value}"

        raw_path = Path(output_file)

        # Enforce that extension matches the requested format to prevent malicious executable creation
        expected_suffix = f".{fmt.value}"
        if raw_path.suffix.lower() != expected_suffix:
            raw_path = raw_path.with_suffix(expected_suffix)

        # Disallow dangerous paths (null bytes, traversal sequences)
        if "\0" in str(raw_path):
            raise ValueError("Invalid null byte in export path")

        target_path = raw_path.resolve()

        # Disallow overwriting critical operating system directories (cross-platform check)
        norm_posix = target_path.as_posix().lower()
        # Strip Windows drive letter if present for unified root checking
        path_without_drive = re.sub(r"^[a-z]:", "", norm_posix)
        forbidden_prefixes = (
            "/etc",
            "/bin",
            "/sbin",
            "/usr",
            "/root",
            "/var",
            "/windows",
            "/program files",
        )
        if path_without_drive.startswith(forbidden_prefixes) or norm_posix.startswith(
            ("c:/windows", "c:/program files")
        ):
            raise PermissionError(
                f"Writing to protected system directory is forbidden: {target_path}"
            )

        target_path.parent.mkdir(parents=True, exist_ok=True)
        return target_path

    async def export_data(
        self,
        fmt: ExportFormat = ExportFormat.CSV,
        city: str | None = None,
        output_file: str | None = None,
    ) -> Path:
        """Export hotels from database into the target file format."""
        await self.db_manager.create_tables()

        async with self.db_manager.session() as session:
            repo = HotelRepository(session)
            hotels: Sequence[Hotel] = await repo.get_hotels_for_export(city=city)

        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        prefix = f"hotels_{city.lower()}" if city else "hotels_all"
        target_path = self._resolve_safe_export_path(
            output_file, fmt, f"{prefix}_{timestamp}"
        )

        if fmt == ExportFormat.JSON:
            data = [self._hotel_to_dict(h) for h in hotels]
            target_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        else:
            # CSV export
            fieldnames = [
                "place_id",
                "name",
                "category",
                "full_address",
                "city",
                "country",
                "latitude",
                "longitude",
                "phone",
                "website",
                "rating",
                "review_count",
                "price_level",
                "check_in_info",
                "amenities",
                "photo_urls",
                "google_maps_url",
                "scraped_at",
            ]
            with open(target_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for h in hotels:
                    row = self._hotel_to_dict(h)
                    # Convert lists to semicolon separated strings for clean CSV representation
                    row["amenities"] = "; ".join(row["amenities"])
                    row["photo_urls"] = "; ".join(row["photo_urls"])
                    # Sanitize each cell against CSV formula injection
                    sanitized_row = {
                        k: self._sanitize_csv_cell(v) for k, v in row.items()
                    }
                    writer.writerow(sanitized_row)

        logger.info(
            "data_export_completed",
            format=fmt.value,
            count=len(hotels),
            path=str(target_path),
        )
        return target_path
