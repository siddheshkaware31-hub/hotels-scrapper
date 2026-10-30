"""Google Places API (New) pluggable provider implementation."""

import os
from datetime import UTC, datetime

import httpx
import structlog

from src.config import Settings
from src.models.schemas import HotelCandidate, HotelData
from src.pipeline.grid import SearchQueryTarget
from src.providers.base import BaseHotelProvider

logger = structlog.get_logger(__name__)


class GooglePlacesApiProvider(BaseHotelProvider):
    """Official Google Places API (New) data provider implementing the shared interface."""

    BASE_URL = "https://places.googleapis.com/v1"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.api_key = settings.google_places_api_key or os.getenv(
            settings.providers.google_places_api.api_key_env_var, ""
        )
        self.client: httpx.AsyncClient | None = None

    async def initialize(self) -> None:
        """Create async HTTP client."""
        if not self.api_key:
            raise ValueError(
                f"Google Places API key missing. Set {self.settings.providers.google_places_api.api_key_env_var} in .env"
            )
        self.client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={
                "X-Goog-Api-Key": self.api_key,
                "Content-Type": "application/json",
            },
            timeout=20.0,
        )
        logger.info("google_places_api_provider_initialized")

    async def search_candidates(
        self, target: SearchQueryTarget
    ) -> list[HotelCandidate]:
        """Query Google Places TextSearch API."""
        if not self.client:
            await self.initialize()
        assert self.client is not None

        endpoint = "/places:searchText"
        headers = {
            "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress",
        }
        payload = {
            "textQuery": target.query_text,
            "languageCode": self.settings.providers.google_places_api.language_code,
        }

        if target.center_lat is not None and target.center_lng is not None:
            payload["locationBias"] = {
                "circle": {
                    "center": {
                        "latitude": target.center_lat,
                        "longitude": target.center_lng,
                    },
                    "radius": 2500.0,
                }
            }

        response = await self.client.post(endpoint, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

        candidates: list[HotelCandidate] = []
        for place in data.get("places", []):
            place_id = place.get("id")
            display_name = place.get("displayName", {}).get("text", "")
            maps_url = f"https://www.google.com/maps/place/?q=place_id:{place_id}"
            candidates.append(
                HotelCandidate(
                    place_id=place_id,
                    google_maps_url=maps_url,
                    area_query=target.query_text,
                    name_hint=display_name,
                )
            )

        logger.info(
            "google_places_api_search_completed",
            query=target.query_text,
            results_count=len(candidates),
        )
        return candidates

    async def get_hotel_details(
        self,
        candidate: HotelCandidate,
        city_context: str | None = None,
        country_context: str | None = None,
    ) -> HotelData:
        """Fetch detailed place properties using Place Details (New)."""
        if not self.client:
            await self.initialize()
        assert self.client is not None

        place_id = candidate.place_id
        if not place_id:
            raise ValueError(
                f"Candidate {candidate.google_maps_url} has no place_id for Places API"
            )

        endpoint = f"/places/{place_id}"
        field_mask = (
            "id,displayName,primaryTypeDisplayName,formattedAddress,location,"
            "nationalPhoneNumber,websiteUri,rating,userRatingCount,priceLevel,"
            "regularOpeningHours,photos"
        )
        headers = {
            "X-Goog-FieldMask": field_mask,
            "X-Goog-Api-Key": self.api_key,
        }

        response = await self.client.get(endpoint, headers=headers)
        response.raise_for_status()
        data = response.json()

        # Parse photo references - DO NOT append api_key to stored URLs (prevent secret leakage)
        photo_urls = []
        for photo in data.get("photos", [])[:5]:
            photo_name = photo.get("name")
            if photo_name:
                photo_urls.append(
                    f"{self.BASE_URL}/{photo_name}/media?maxHeightPx=600&maxWidthPx=800"
                )

        loc = data.get("location", {})
        lat = loc.get("latitude")
        lng = loc.get("longitude")

        hours_data = data.get("regularOpeningHours", {})
        descriptions = hours_data.get("weekdayDescriptions", [])
        check_in_info = "; ".join(descriptions) if descriptions else None

        hotel = HotelData(
            place_id=place_id,
            name=data.get("displayName", {}).get(
                "text", candidate.name_hint or "Unknown"
            ),
            category=data.get("primaryTypeDisplayName", {}).get("text", "Hotel"),
            full_address=data.get("formattedAddress"),
            city=city_context,
            country=country_context,
            latitude=lat,
            longitude=lng,
            phone=data.get("nationalPhoneNumber"),
            website=data.get("websiteUri"),
            rating=data.get("rating"),
            review_count=data.get("userRatingCount"),
            price_level=data.get("priceLevel"),
            check_in_info=check_in_info,
            amenities=[],
            photo_urls=photo_urls,
            google_maps_url=candidate.google_maps_url,
            scraped_at=datetime.now(UTC),
        )
        return hotel

    async def close(self) -> None:
        """Close HTTP client session."""
        if self.client:
            await self.client.aclose()
            self.client = None
            logger.info("google_places_api_provider_closed")
