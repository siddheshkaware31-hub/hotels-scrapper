"""Playwright async browser manager with persistent contexts and stealth patches."""

import itertools
from pathlib import Path

import structlog
from playwright.async_api import (
    BrowserContext,
    Playwright,
    async_playwright,
)

from src.config import ScraperConfig
from src.providers.google_maps.anti_detect import AntiDetectManager

logger = structlog.get_logger(__name__)


# Lightweight stealth script to prevent immediate bot flags
STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined,
});
window.chrome = {
    runtime: {},
    loadTimes: function() {},
    csi: function() {},
    app: {}
};
Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5],
});
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en'],
});
"""


class BrowserManager:
    """Manages Playwright async lifecycle, anti-bot context settings, and proxy rotation."""

    def __init__(self, config: ScraperConfig):
        self.config = config
        self.anti_detect = AntiDetectManager(
            rotate_ua=config.anti_bot.rotate_user_agents
        )
        self._playwright: Playwright | None = None
        self._proxy_cycle = None
        if config.proxies.enabled and config.proxies.list:
            self._proxy_cycle = itertools.cycle(config.proxies.list)

    def _get_next_proxy_dict(self) -> dict | None:
        """Format proxy string for Playwright if enabled."""
        if not self.config.proxies.enabled or not self._proxy_cycle:
            return None
        proxy_url = next(self._proxy_cycle)
        return {"server": proxy_url}

    async def initialize(self) -> None:
        """Start Playwright runtime."""
        if not self._playwright:
            self._playwright = await async_playwright().start()
            logger.info("playwright_runtime_started")

    async def create_context(self, user_agent: str | None = None) -> BrowserContext:
        """Create a resilient, stealth-injected browser context."""
        if not self._playwright:
            await self.initialize()

        assert self._playwright is not None

        ua = user_agent or self.anti_detect.get_random_user_agent()
        proxy = self._get_next_proxy_dict()

        user_data_path = Path(self.config.user_data_dir)
        user_data_path.mkdir(parents=True, exist_ok=True)

        # Launch persistent context to reuse cookies, cache, and reduce bot flags
        context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(user_data_path),
            headless=self.config.headless,
            slow_mo=self.config.slow_mo_ms,
            viewport={
                "width": self.config.viewport.width,
                "height": self.config.viewport.height,
            },
            user_agent=ua,
            locale=self.config.locale,
            timezone_id=self.config.timezone_id,
            proxy=proxy,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-infobars",
                "--disable-dev-shm-usage",
                "--lang=en-US,en",
            ],
            ignore_default_args=["--enable-automation"],
        )

        # Inject stealth evasions into all pages
        await context.add_init_script(STEALTH_JS)

        # Handle Google Consent Interstitial automatically if it pops up
        context.on("page", self._on_new_page)

        logger.info(
            "browser_context_created",
            headless=self.config.headless,
            has_proxy=bool(proxy),
            user_data_dir=str(user_data_path),
        )
        return context

    def _on_new_page(self, page):
        """Register listeners for consent modal dismissal on any newly created page."""
        page.on("domcontentloaded", lambda: self._dismiss_consent(page))

    async def _dismiss_consent(self, page):
        """Silently dismiss European or regional 'Before you continue to Google' dialogs."""
        consent_selectors = [
            "form[action*='consent.google'] button",
            "button[aria-label*='Accept all']",
            "button:has-text('Accept all')",
            "button:has-text('I agree')",
        ]
        for sel in consent_selectors:
            try:
                btn = page.locator(sel).first
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.click()
                    logger.info("google_consent_modal_dismissed")
                    break
            except Exception:
                pass

    async def close(self) -> None:
        """Stop Playwright engine cleanly."""
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
            logger.info("playwright_runtime_stopped")
