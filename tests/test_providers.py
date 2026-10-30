"""Unit tests for pluggable provider interface and provider switching."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.config import Settings
from src.models.schemas import HotelData
from src.pipeline.grid import SearchQueryTarget
from src.providers import get_provider
from src.providers.base import BaseHotelProvider
from src.providers.google_maps.provider import GoogleMapsPlaywrightProvider
from src.providers.google_places_api.provider import GooglePlacesApiProvider


def test_provider_factory_selection(sample_settings: Settings):
    # Test default Playwright provider
    p1 = get_provider(sample_settings, "google_maps_playwright")
    assert isinstance(p1, BaseHotelProvider)
    assert isinstance(p1, GoogleMapsPlaywrightProvider)

    # Test Google Places API provider
    sample_settings.google_places_api_key = "fake_api_key"
    p2 = get_provider(sample_settings, "google_places_api")
    assert isinstance(p2, BaseHotelProvider)
    assert isinstance(p2, GooglePlacesApiProvider)


@pytest.mark.asyncio
async def test_google_places_api_provider_contract(sample_settings: Settings):
    sample_settings.google_places_api_key = "test_key_123"
    provider = GooglePlacesApiProvider(sample_settings)

    # Mock client and HTTP responses
    mock_client = AsyncMock()
    provider.client = mock_client

    # 1. Search mock response
    mock_search_response = MagicMock()
    mock_search_response.json.return_value = {
        "places": [
            {
                "id": "ChIJ_mock_123",
                "displayName": {"text": "API Luxury Suites"},
                "formattedAddress": "Marine Lines, Mumbai, India",
            }
        ]
    }
    mock_search_response.raise_for_status = MagicMock()
    mock_client.post.return_value = mock_search_response

    target = SearchQueryTarget(
        query_text="hotels in Marine Lines", region_name="Mumbai"
    )
    candidates = await provider.search_candidates(target)

    assert len(candidates) == 1
    assert candidates[0].place_id == "ChIJ_mock_123"
    assert "API Luxury Suites" in candidates[0].name_hint

    # 2. Detail mock response
    mock_detail_response = MagicMock()
    mock_detail_response.json.return_value = {
        "id": "ChIJ_mock_123",
        "displayName": {"text": "API Luxury Suites"},
        "primaryTypeDisplayName": {"text": "Hotel"},
        "formattedAddress": "Marine Lines, Mumbai, Maharashtra 400020, India",
        "location": {"latitude": 18.943, "longitude": 72.823},
        "nationalPhoneNumber": "+91 22 2200 0000",
        "websiteUri": "https://apiluxury.example.com",
        "rating": 4.6,
        "userRatingCount": 350,
        "priceLevel": "PRICE_LEVEL_EXPENSIVE",
        "regularOpeningHours": {"weekdayDescriptions": ["Open 24 hours"]},
        "photos": [{"name": "places/ChIJ_mock_123/photos/sample_ref"}],
    }
    mock_detail_response.raise_for_status = MagicMock()
    mock_client.get.return_value = mock_detail_response

    hotel = await provider.get_hotel_details(
        candidates[0],
        city_context="Mumbai",
        country_context="India",
    )

    assert isinstance(hotel, HotelData)
    assert hotel.place_id == "ChIJ_mock_123"
    assert hotel.name == "API Luxury Suites"
    assert hotel.latitude == 18.943
    assert hotel.longitude == 72.823
    assert hotel.rating == 4.6
    assert hotel.review_count == 350
    assert len(hotel.photo_urls) == 1
    assert "sample_ref" in hotel.photo_urls[0]
    # Verify API key is NOT leaked in persisted URLs
    assert "test_key_123" not in hotel.photo_urls[0]
