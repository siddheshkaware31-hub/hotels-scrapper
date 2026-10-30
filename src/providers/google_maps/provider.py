"""Playwright-based Google Maps implementation of BaseHotelProvider."""

import structlog
from playwright.async_api import BrowserContext

from src.config import Settings
from src.models.schemas import HotelCandidate, HotelData
from src.pipeline.grid import SearchQueryTarget
from src.providers.base import BaseHotelProvider
from src.providers.google_maps.browser import BrowserManager
from src.providers.google_maps.detail import DetailPageExtractor
from src.providers.google_maps.search import SearchFeedScraper

logger = structlog.get_logger(__name__)


class GoogleMapsPlaywrightProvider(BaseHotelProvider):
    """Production Playwright scraper provider for Google Maps."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.browser_manager = BrowserManager(settings.scraper)
        self.search_scraper = SearchFeedScraper(
            anti_detect=self.browser_manager.anti_detect,
            snapshots_dir=settings.app.snapshots_dir,
        )
        self.detail_extractor = DetailPageExtractor(
            anti_detect=self.browser_manager.anti_detect,
            snapshots_dir=settings.app.snapshots_dir,
        )
        self._context: BrowserContext | None = None

    async def initialize(self) -> None:
        """Initialize browser and create default persistent context."""
        await self.browser_manager.initialize()
        self._context = await self.browser_manager.create_context()
        logger.info("google_maps_playwright_provider_initialized")

    async def search_candidates(
        self, target: SearchQueryTarget
    ) -> list[HotelCandidate]:
        """Execute map search and scroll feed to gather place permalinks."""
        if not self._context:
            await self.initialize()
        assert self._context is not None

        page = await self._context.new_page()
        try:
            candidates = await self.search_scraper.collect_places_from_query(
                page=page,
                query=target.query_text,
                direct_url=target.direct_search_url,
            )
            return candidates
        finally:
            try:
                if page and not page.is_closed():
                    await page.close()
            except Exception:
                pass

    async def get_hotel_details(
        self,
        candidate: HotelCandidate,
        city_context: str | None = None,
        country_context: str | None = None,
    ) -> HotelData:
        """Visit individual place page and extract complete hotel data model."""
        if not self._context:
            await self.initialize()
        assert self._context is not None

        page = await self._context.new_page()
        try:
            hotel = await self.detail_extractor.extract_hotel_details(
                page=page,
                url=candidate.google_maps_url,
                city_context=city_context,
                country_context=country_context,
            )
            return hotel
        finally:
            try:
                if page and not page.is_closed():
                    await page.close()
            except Exception:
                pass

    async def close(self) -> None:
        """Close browser context and shut down Playwright."""
        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
            self._context = None
        await self.browser_manager.close()
        logger.info("google_maps_playwright_provider_closed")
