"""Google Maps search feed scroller and place candidate collector."""

import structlog
from playwright.async_api import Page

from src.models.schemas import HotelCandidate
from src.providers.google_maps.anti_detect import (
    AntiDetectManager,
    CaptchaDetectedException,
)
from src.providers.google_maps.selectors import GoogleMapsSelectors
from src.utils.security import is_safe_maps_url
from src.utils.snapshot import save_failure_snapshot

logger = structlog.get_logger(__name__)


class SearchFeedScraper:
    """Navigates to Google Maps search, scrolls the results feed, and yields hotel candidates."""

    def __init__(
        self, anti_detect: AntiDetectManager, snapshots_dir: str = "snapshots"
    ):
        self.anti_detect = anti_detect
        self.snapshots_dir = snapshots_dir

    async def collect_places_from_query(
        self,
        page: Page,
        query: str,
        direct_url: str | None = None,
        max_scroll_attempts: int = 40,
        stagnation_limit: int = 5,
    ) -> list[HotelCandidate]:
        """Execute search, auto-scroll feed to completion, and return discovered hotel candidates."""
        url = (
            direct_url
            or f"https://www.google.com/maps/search/{query.replace(' ', '+')}?entry=ttu"
        )
        if not is_safe_maps_url(url):
            raise ValueError(
                f"Security rejection: Invalid or untrusted search URL: {url}"
            )
        logger.info("navigating_to_search", query=query, url=url)

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await self.anti_detect.human_delay(2.0, 3.5)
            await self.anti_detect.check_captcha_or_block(page)

            # Wait for search feed or individual place links
            feed_locator = None
            for sel in GoogleMapsSelectors.FEED_CONTAINER:
                locator = page.locator(sel).first
                if await locator.count() > 0:
                    feed_locator = locator
                    break

            if not feed_locator:
                # If single place directly opened, extract current URL if it's a place
                if "/maps/place/" in page.url:
                    logger.info("search_redirected_directly_to_place", url=page.url)
                    return [HotelCandidate(google_maps_url=page.url, area_query=query)]
                logger.warning("search_feed_not_found_waiting_cards", query=query)

            collected_urls: set[str] = set()
            candidates: list[HotelCandidate] = []
            consecutive_no_new_items = 0

            for scroll_idx in range(max_scroll_attempts):
                await self.anti_detect.check_captcha_or_block(page)

                # Extract newly visible place cards
                anchors = await page.locator("a[href*='/maps/place/']").all()
                new_found_this_step = 0

                for a in anchors:
                    href = await a.get_attribute("href")
                    if href and href not in collected_urls:
                        # Clean permalink
                        clean_href = href.split("?")[0] if "?" in href else href
                        collected_urls.add(href)
                        title = await a.get_attribute("aria-label") or ""
                        candidates.append(
                            HotelCandidate(
                                google_maps_url=href,
                                area_query=query,
                                name_hint=title.strip() if title else None,
                            )
                        )
                        new_found_this_step += 1

                logger.debug(
                    "feed_scroll_progress",
                    scroll_idx=scroll_idx,
                    new_found=new_found_this_step,
                    total_collected=len(candidates),
                )

                # Check for explicit end-of-list marker (using .first to avoid strict mode violations)
                at_end = False
                for end_marker in GoogleMapsSelectors.END_OF_LIST_INDICATORS:
                    try:
                        marker_loc = page.locator(end_marker).first
                        if await marker_loc.count() > 0 and await marker_loc.is_visible():
                            logger.info(
                                "end_of_search_feed_reached",
                                query=query,
                                total=len(candidates),
                            )
                            at_end = True
                            break
                    except Exception:
                        continue

                if at_end:
                    break

                # Detect scroll stagnation
                if new_found_this_step == 0:
                    consecutive_no_new_items += 1
                else:
                    consecutive_no_new_items = 0

                if consecutive_no_new_items >= stagnation_limit:
                    logger.info(
                        "scroll_stagnation_reached_stopping", total=len(candidates)
                    )
                    break

                # Perform scroll action
                if feed_locator:
                    await feed_locator.evaluate("el => el.scrollBy(0, 1200)")
                else:
                    await page.mouse.wheel(0, 1200)

                await self.anti_detect.human_delay(1.5, 2.8)

            logger.info(
                "search_query_collection_complete",
                query=query,
                candidates_count=len(candidates),
            )
            return candidates

        except CaptchaDetectedException:
            await save_failure_snapshot(
                page, f"captcha_search_{query}", self.snapshots_dir
            )
            raise
        except Exception as e:
            logger.error("search_feed_scraping_error", error=str(e), query=query)
            await save_failure_snapshot(
                page, f"error_search_{query}", self.snapshots_dir
            )
            return []
