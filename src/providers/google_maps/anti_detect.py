"""Anti-bot, CAPTCHA detection, and user-agent rotation module."""

import asyncio
import random

import structlog
from fake_useragent import UserAgent
from playwright.async_api import Page

from src.providers.google_maps.selectors import GoogleMapsSelectors

logger = structlog.get_logger(__name__)


class CaptchaDetectedException(Exception):
    """Raised when Google presents a CAPTCHA or 'unusual traffic' block page."""

    def __init__(self, message: str, url: str):
        super().__init__(message)
        self.url = url


class AntiDetectManager:
    """Handles client fingerprints, randomized delays, and defensive block detection."""

    FALLBACK_USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    ]

    def __init__(self, rotate_ua: bool = True):
        self.rotate_ua = rotate_ua
        self._ua_generator: UserAgent | None = None
        if rotate_ua:
            try:
                self._ua_generator = UserAgent(browsers=["chrome", "edge"])
            except Exception as e:
                logger.warning("ua_generator_init_failed_using_fallbacks", error=str(e))

    def get_random_user_agent(self) -> str:
        """Return a random modern desktop User-Agent string."""
        if self._ua_generator:
            try:
                ua = self._ua_generator.random
                if ua:
                    return ua
            except Exception:
                pass
        return random.choice(self.FALLBACK_USER_AGENTS)

    async def check_captcha_or_block(self, page: Page) -> None:
        """Inspect the current page for Google CAPTCHA or unusual traffic warnings."""
        current_url = page.url

        # Check URL pattern for google /sorry/index
        if "/sorry/index" in current_url:
            logger.critical("captcha_block_detected_url", url=current_url)
            raise CaptchaDetectedException(
                "Google redirected to /sorry/index CAPTCHA page",
                url=current_url,
            )

        # Inspect DOM for known CAPTCHA elements
        for selector in GoogleMapsSelectors.BOT_DETECTION:
            try:
                locator = page.locator(selector).first
                if await locator.count() > 0:
                    is_visible = await locator.is_visible()
                    if is_visible:
                        logger.critical(
                            "captcha_block_detected_dom",
                            selector=selector,
                            url=current_url,
                        )
                        raise CaptchaDetectedException(
                            f"Bot detection trigger matched selector: {selector}",
                            url=current_url,
                        )
            except CaptchaDetectedException:
                raise
            except Exception:
                continue

    async def human_delay(self, min_sec: float = 2.0, max_sec: float = 4.5) -> float:
        """Introduce randomized human-like pause."""
        delay = round(random.uniform(min_sec, max_sec), 2)
        await asyncio.sleep(delay)
        return delay
