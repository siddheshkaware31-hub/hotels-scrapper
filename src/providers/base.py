"""Abstract Base Provider interface for pluggable hotel data acquisition."""

from abc import ABC, abstractmethod

from src.models.schemas import HotelCandidate, HotelData
from src.pipeline.grid import SearchQueryTarget


class BaseHotelProvider(ABC):
    """Contract that any hotel data source (Scraper, Official API, etc.) must implement."""

    @abstractmethod
    async def initialize(self) -> None:
        """Perform provider setup, connection pool or browser initialization."""

    @abstractmethod
    async def search_candidates(
        self, target: SearchQueryTarget
    ) -> list[HotelCandidate]:
        """Search for hotel candidates matching the target area query."""

    @abstractmethod
    async def get_hotel_details(
        self,
        candidate: HotelCandidate,
        city_context: str | None = None,
        country_context: str | None = None,
    ) -> HotelData:
        """Retrieve complete hotel attributes for a candidate."""

    @abstractmethod
    async def close(self) -> None:
        """Teardown sessions, contexts, or network connections."""
