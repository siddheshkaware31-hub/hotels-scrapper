"""Unit tests for the geographic grid query generator."""

from src.config import BoundingBoxConfig, RegionConfig
from src.pipeline.grid import GridQueryGenerator


def test_generate_grid_cells_counts():
    """Verify that grid calculation generates sensible coordinate cells."""
    min_lat, max_lat = 18.90, 19.20
    min_lng, max_lng = 72.80, 73.00
    step_km = 10.0  # ~0.09 degrees

    cells = GridQueryGenerator.generate_grid_cells(
        min_lat=min_lat,
        max_lat=max_lat,
        min_lng=min_lng,
        max_lng=max_lng,
        step_km=step_km,
    )

    assert len(cells) > 0
    for lat, lng in cells:
        assert min_lat <= lat <= max_lat + 0.1
        assert min_lng <= lng <= max_lng + 0.1


def test_generate_targets_for_grid_strategy():
    """Verify search targets generation for grid-enabled region."""
    region = RegionConfig(
        name="Mumbai",
        country="India",
        strategy="grid",
        bbox=BoundingBoxConfig(
            min_lat=18.90,
            max_lat=19.10,
            min_lng=72.80,
            max_lng=72.90,
        ),
        grid_step_km=8.0,
        neighborhoods=["Colaba"],
    )

    targets = GridQueryGenerator.generate_targets_for_region(region)
    assert len(targets) >= 1
    # Check that direct_search_url contains coordinates
    assert any(
        "https://www.google.com/maps/search/hotels/@" in t.direct_search_url
        for t in targets
        if t.direct_search_url
    )


def test_generate_targets_for_neighborhoods_strategy():
    """Verify search targets for neighborhood-only strategy."""
    region = RegionConfig(
        name="Dubai",
        country="UAE",
        strategy="neighborhoods",
        neighborhoods=["Downtown Dubai", "Marina"],
    )

    targets = GridQueryGenerator.generate_targets_for_region(region)
    assert len(targets) == 2
    assert targets[0].query_text == "hotels in Downtown Dubai"
    assert targets[1].query_text == "hotels in Marina"
