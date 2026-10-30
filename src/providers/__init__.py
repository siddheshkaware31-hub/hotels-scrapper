"""Providers registry and factory."""

from src.config import Settings
from src.providers.base import BaseHotelProvider
from src.providers.google_maps.provider import GoogleMapsPlaywrightProvider
from src.providers.google_places_api.provider import GooglePlacesApiProvider


def get_provider(
    settings: Settings, provider_name: str | None = None
) -> BaseHotelProvider:
    """Instantiate the active or requested provider."""
    name = provider_name or settings.providers.active

    if name == "google_places_api":
        return GooglePlacesApiProvider(settings)
    elif name == "google_maps_playwright":
        return GoogleMapsPlaywrightProvider(settings)
    else:
        raise ValueError(
            f"Unknown hotel provider: {name}. Supported: 'google_maps_playwright', 'google_places_api'"
        )


__all__ = [
    "BaseHotelProvider",
    "GoogleMapsPlaywrightProvider",
    "GooglePlacesApiProvider",
    "get_provider",
]
