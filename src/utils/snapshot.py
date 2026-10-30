"""Snapshot saver for failed extractions and debugging."""

import re
from datetime import UTC, datetime
from pathlib import Path

import structlog
from playwright.async_api import Page

logger = structlog.get_logger(__name__)


def sanitize_filename(name: str) -> str:
    """Sanitize strings for filesystem safety, stripping directory traversal tokens."""
    cleaned = re.sub(r"[^a-zA-Z0-9_\-]", "_", name).strip("_")
    return cleaned[:60] if cleaned else "unknown"


async def save_failure_snapshot(
    page: Page | None,
    identifier: str,
    snapshots_dir: str = "snapshots",
    html_content: str | None = None,
) -> dict[str, str]:
    """Save raw page HTML and an optional screenshot when extraction encounters an issue."""
    target_dir = Path(snapshots_dir).resolve()
    # Guard against accidental root directory snapshots
    if str(target_dir).lower() in ["c:\\", "c:\\windows", "/", "/etc", "/bin"]:
        target_dir = Path("snapshots").resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    clean_id = sanitize_filename(identifier)
    base_filename = f"failure_{clean_id}_{timestamp}"

    results = {}

    html_path = target_dir / f"{base_filename}.html"
    try:
        if page and not page.is_closed():
            content = await page.content()
        else:
            content = html_content or "<!-- No HTML available -->"

        html_path.write_text(content, encoding="utf-8")
        results["html_path"] = str(html_path)
    except Exception as e:
        logger.warning("snapshot_html_failed", error=str(e), identifier=identifier)

    if page and not page.is_closed():
        screenshot_path = target_dir / f"{base_filename}.png"
        try:
            await page.screenshot(path=str(screenshot_path), full_page=False)
            results["screenshot_path"] = str(screenshot_path)
        except Exception as e:
            logger.warning(
                "snapshot_screenshot_failed", error=str(e), identifier=identifier
            )

    logger.info("failure_snapshot_saved", identifier=identifier, **results)
    return results
