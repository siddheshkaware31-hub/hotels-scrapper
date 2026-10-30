"""Google Maps place detail page extractor using resilient selector chains."""

import re
from datetime import UTC, datetime

import structlog
from playwright.async_api import Page

from src.models.schemas import HotelData
from src.providers.google_maps.anti_detect import (
    AntiDetectManager,
    CaptchaDetectedException,
)
from src.providers.google_maps.selectors import (
    CID_REGEX,
    LAT_LNG_URL_REGEX,
    PLACE_ID_CH_REGEX,
    PLACE_ID_HEX_REGEX,
    GoogleMapsSelectors,
)
from src.utils.security import is_safe_maps_url
from src.utils.snapshot import save_failure_snapshot

logger = structlog.get_logger(__name__)


class DetailPageExtractor:
    """Extracts standardized hotel metadata from individual Google Maps place pages."""

    def __init__(
        self, anti_detect: AntiDetectManager, snapshots_dir: str = "snapshots"
    ):
        self.anti_detect = anti_detect
        self.snapshots_dir = snapshots_dir

    async def _safe_text_or_attr(
        self,
        page: Page,
        selectors: list[str],
        attribute: str | None = None,
        regex_pattern: re.Pattern | None = None,
        timeout: int = 1200,
    ) -> str | None:
        """Try selector alternatives in order; extract attribute or innerText with optional regex."""
        for sel in selectors:
            try:
                locator = page.locator(sel).first
                if await locator.count() > 0:
                    val: str | None = None
                    if attribute:
                        val = await locator.get_attribute(attribute, timeout=timeout)
                    if not val:
                        val = await locator.text_content(timeout=timeout)

                    if val:
                        cleaned = val.strip()
                        if regex_pattern:
                            match = regex_pattern.search(cleaned)
                            if match:
                                return match.group(1).replace(",", "")
                            continue
                        return cleaned
            except Exception:
                continue
        return None

    def _extract_coordinates_from_url(
        self, url: str
    ) -> tuple[float | None, float | None]:
        """Extract latitude and longitude floating point coordinates from URL."""
        match = LAT_LNG_URL_REGEX.search(url)
        if match:
            try:
                return float(match.group(1)), float(match.group(2))
            except ValueError:
                pass
        return None, None

    def _extract_place_id(self, url: str, html_snippet: str = "") -> str:
        """Derive place_id or CID hex identifier from the permalink or DOM."""
        hex_match = PLACE_ID_HEX_REGEX.search(url)
        if hex_match:
            return hex_match.group(1)

        cid_match = CID_REGEX.search(url)
        if cid_match:
            return f"cid_{cid_match.group(1)}"

        # Look for ChI place id in URL or HTML
        ch_match = PLACE_ID_CH_REGEX.search(url)
        if ch_match:
            return ch_match.group(1)

        # Fallback to deterministic hash of the base URL
        import hashlib

        clean_url = url.split("?")[0]
        return f"gen_{hashlib.md5(clean_url.encode('utf-8')).hexdigest()[:16]}"

    def _parse_address_components(
        self,
        full_address: str | None,
        default_city: str | None = None,
        default_country: str | None = None,
    ) -> tuple[str | None, str | None]:
        """Infer city and country from comma-separated address string."""
        city = default_city
        country = default_country

        if full_address:
            parts = [p.strip() for p in full_address.split(",") if p.strip()]
            if len(parts) >= 2:
                # The last item is often country or postal code + country
                country_candidate = parts[-1]
                # Remove postal codes if attached
                cleaned_country = re.sub(r"\d+", "", country_candidate).strip()
                if cleaned_country:
                    country = cleaned_country

                # Preceding item is typically city / state
                city_candidate = parts[-2]
                cleaned_city = re.sub(r"\d+", "", city_candidate).strip()
                if cleaned_city:
                    city = cleaned_city

        return city, country

    async def extract_hotel_details(
        self,
        page: Page,
        url: str,
        city_context: str | None = None,
        country_context: str | None = None,
    ) -> HotelData:
        """Visit place URL, parse all canonical hotel properties with per-field resilience."""
        logger.info("extracting_hotel_details", url=url)

        if not is_safe_maps_url(url):
            raise ValueError(
                f"Security rejection: Untrusted or non-Google navigation target URL: {url}"
            )

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await self.anti_detect.human_delay(1.5, 3.0)
            await self.anti_detect.check_captcha_or_block(page)

            # Wait for main content or title
            try:
                await page.wait_for_selector("h1", timeout=10000)
            except Exception:
                logger.warning("h1_not_found_continuing_extraction", url=url)

            # 1. Place ID
            place_id = self._extract_place_id(page.url)

            # 2. Name
            name = await self._safe_text_or_attr(
                page, GoogleMapsSelectors.NAME.selectors
            )
            if not name:
                # Fallback: check document title
                title = await page.title()
                if title and "-" in title:
                    name = title.split("-")[0].strip()
                else:
                    name = title.strip() if title else "Unknown Hotel"

            # 3. Category
            category = (
                await self._safe_text_or_attr(
                    page,
                    GoogleMapsSelectors.CATEGORY.selectors,
                )
                or "Hotel"
            )

            # 4. Address
            full_address = await self._safe_text_or_attr(
                page,
                GoogleMapsSelectors.ADDRESS.selectors,
                attribute=GoogleMapsSelectors.ADDRESS.attribute,
            )
            if full_address and full_address.lower().startswith("address:"):
                full_address = full_address.split(":", 1)[1].strip()

            city, country = self._parse_address_components(
                full_address,
                default_city=city_context,
                default_country=country_context,
            )

            # 5. Coordinates
            lat, lng = self._extract_coordinates_from_url(page.url)

            # 6. Phone
            phone = await self._safe_text_or_attr(
                page,
                GoogleMapsSelectors.PHONE.selectors,
                attribute=GoogleMapsSelectors.PHONE.attribute,
            )
            if phone and phone.lower().startswith("phone:"):
                phone = phone.split(":", 1)[1].strip()

            # 7. Website
            website = await self._safe_text_or_attr(
                page,
                GoogleMapsSelectors.WEBSITE.selectors,
                attribute="href",
            )
            if website and "/url?q=" in website:
                # Clean Google redirect links
                match = re.search(r"/url\?q=([^&]+)", website)
                if match:
                    website = match.group(1)

            # 8. Rating
            rating_raw = await self._safe_text_or_attr(
                page,
                GoogleMapsSelectors.RATING.selectors,
                attribute=GoogleMapsSelectors.RATING.attribute,
                regex_pattern=GoogleMapsSelectors.RATING.regex_pattern,
            )
            rating: float | None = None
            if rating_raw:
                try:
                    rating = float(rating_raw.replace(",", "."))
                except ValueError:
                    pass

            # 9. Review Count
            review_raw = await self._safe_text_or_attr(
                page,
                GoogleMapsSelectors.REVIEW_COUNT.selectors,
                attribute=GoogleMapsSelectors.REVIEW_COUNT.attribute,
                regex_pattern=GoogleMapsSelectors.REVIEW_COUNT.regex_pattern,
            )
            review_count: int | None = None
            if review_raw:
                try:
                    review_count = int(review_raw)
                except ValueError:
                    pass

            # 10. Price Level
            price_level = await self._safe_text_or_attr(
                page,
                GoogleMapsSelectors.PRICE_LEVEL.selectors,
            )

            # 11. Check-in Info / Opening Hours
            check_in_info = await self._safe_text_or_attr(
                page,
                GoogleMapsSelectors.CHECK_IN_INFO.selectors,
                attribute=GoogleMapsSelectors.CHECK_IN_INFO.attribute,
            )

            # 12. Amenities
            amenities: list[str] = []
            for sel in GoogleMapsSelectors.AMENITIES_CONTAINER:
                try:
                    elements = await page.locator(f"{sel} span, {sel} div").all()
                    for el in elements:
                        txt = await el.text_content()
                        if txt:
                            txt = txt.strip()
                            if 3 < len(txt) < 40 and txt not in amenities:
                                amenities.append(txt)
                    if amenities:
                        break
                except Exception:
                    continue

            # 13. Photos (up to 5)
            photo_urls: list[str] = []
            for sel in GoogleMapsSelectors.PHOTO_ELEMENTS:
                try:
                    imgs = await page.locator(sel).all()
                    for img in imgs:
                        src = await img.get_attribute("src")
                        if (
                            src
                            and "googleusercontent.com" in src
                            and src not in photo_urls
                        ):
                            photo_urls.append(src)
                        if len(photo_urls) >= 5:
                            break
                    if photo_urls:
                        break
                except Exception:
                    continue

            hotel = HotelData(
                place_id=place_id,
                name=name,
                category=category,
                full_address=full_address,
                city=city,
                country=country,
                latitude=lat,
                longitude=lng,
                phone=phone,
                website=website,
                rating=rating,
                review_count=review_count,
                price_level=price_level,
                check_in_info=check_in_info,
                amenities=amenities,
                photo_urls=photo_urls,
                google_maps_url=page.url,
                scraped_at=datetime.now(UTC),
            )

            logger.info(
                "hotel_details_extracted_successfully", place_id=place_id, name=name
            )
            return hotel

        except CaptchaDetectedException:
            await save_failure_snapshot(
                page, f"captcha_detail_{url}", self.snapshots_dir
            )
            raise
        except Exception as e:
            logger.error("hotel_detail_extraction_failed", error=str(e), url=url)
            await save_failure_snapshot(page, f"error_detail_{url}", self.snapshots_dir)
            raise
