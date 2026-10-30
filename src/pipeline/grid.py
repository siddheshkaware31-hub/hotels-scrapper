"""Grid query generator for splitting metropolitan regions into search tiles."""

import math
from dataclasses import dataclass

import structlog

from src.config import RegionConfig

logger = structlog.get_logger(__name__)


@dataclass
class SearchQueryTarget:
    """Represents a discrete search target with an optional geographic coordinate focus."""

    query_text: str
    region_name: str
    center_lat: float | None = None
    center_lng: float | None = None
    zoom_level: int = 15
    direct_search_url: str | None = None


class GridQueryGenerator:
    """Generates search targets based on coordinate grid bounding boxes and neighborhood lists."""

    KM_PER_LAT_DEGREE = 110.574

    @classmethod
    def km_per_lng_degree(cls, latitude: float) -> float:
        """Calculate approximate kilometers per degree of longitude at a given latitude."""
        rad = math.radians(latitude)
        return 111.320 * math.cos(rad)

    MAX_CELLS = 2000

    @classmethod
    def generate_grid_cells(
        cls,
        min_lat: float,
        max_lat: float,
        min_lng: float,
        max_lng: float,
        step_km: float = 3.5,
    ) -> list[tuple[float, float]]:
        """Decompose a bounding box into a grid of (lat, lng) center coordinates."""
        # Sanitize coordinate order
        if min_lat > max_lat:
            min_lat, max_lat = max_lat, min_lat
        if min_lng > max_lng:
            min_lng, max_lng = max_lng, min_lng

        # Clamp to realistic planetary bounds
        min_lat = max(-85.0, min(85.0, min_lat))
        max_lat = max(-85.0, min(85.0, max_lat))
        min_lng = max(-180.0, min(180.0, min_lng))
        max_lng = max(-180.0, min(180.0, max_lng))

        # Enforce minimum positive step to prevent infinite loops (DoS protection)
        safe_step_km = max(0.5, float(step_km))

        mid_lat = (min_lat + max_lat) / 2.0
        lat_step = safe_step_km / cls.KM_PER_LAT_DEGREE
        lng_step = safe_step_km / max(cls.km_per_lng_degree(mid_lat), 1.0)

        # If bounding box is smaller than step, return single center cell
        if (max_lat - min_lat) <= lat_step and (max_lng - min_lng) <= lng_step:
            return [(round(mid_lat, 5), round((min_lng + max_lng) / 2.0, 5))]

        cells: list[tuple[float, float]] = []
        cur_lat = min_lat + (lat_step / 2.0)
        while cur_lat <= max_lat:
            cur_lng = min_lng + (lng_step / 2.0)
            while cur_lng <= max_lng:
                cells.append((round(cur_lat, 5), round(cur_lng, 5)))
                if len(cells) >= cls.MAX_CELLS:
                    logger.warning("grid_cell_limit_reached", max_cells=cls.MAX_CELLS)
                    return cells
                cur_lng += lng_step
            cur_lat += lat_step

        if not cells:
            cells.append((round(mid_lat, 5), round((min_lng + max_lng) / 2.0, 5)))

        return cells

    @classmethod
    def generate_targets_for_region(
        cls, region: RegionConfig
    ) -> list[SearchQueryTarget]:
        """Produce search targets for a configured region."""
        targets: list[SearchQueryTarget] = []

        if region.strategy == "grid" and region.bbox:
            cells = cls.generate_grid_cells(
                min_lat=region.bbox.min_lat,
                max_lat=region.bbox.max_lat,
                min_lng=region.bbox.min_lng,
                max_lng=region.bbox.max_lng,
                step_km=region.grid_step_km,
            )
            logger.info(
                "generated_grid_cells",
                region=region.name,
                cells_count=len(cells),
                step_km=region.grid_step_km,
            )
            for lat, lng in cells:
                # Direct maps search URL focused on the specific coordinate tile
                url = f"https://www.google.com/maps/search/hotels/@{lat},{lng},15z?entry=ttu"
                targets.append(
                    SearchQueryTarget(
                        query_text=f"hotels near {lat:.4f},{lng:.4f} {region.name}",
                        region_name=region.name,
                        center_lat=lat,
                        center_lng=lng,
                        zoom_level=15,
                        direct_search_url=url,
                    )
                )

        # Also add or fallback to neighborhoods
        if region.strategy == "neighborhoods" or not targets:
            for hood in region.neighborhoods:
                query = region.query_template.format(area=hood)
                targets.append(
                    SearchQueryTarget(
                        query_text=query,
                        region_name=region.name,
                        direct_search_url=None,
                    )
                )

        logger.info(
            "region_search_targets_ready",
            region=region.name,
            total_targets=len(targets),
            strategy=region.strategy,
        )
        return targets
