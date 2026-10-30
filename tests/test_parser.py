"""Unit tests for resilient detail extraction, selectors, and anti-bot detection."""

from pathlib import Path

from bs4 import BeautifulSoup

from src.providers.google_maps.anti_detect import AntiDetectManager
from src.providers.google_maps.detail import DetailPageExtractor
from src.providers.google_maps.selectors import (
    LAT_LNG_URL_REGEX,
    PLACE_ID_HEX_REGEX,
    GoogleMapsSelectors,
)


def test_url_regex_extraction():
    """Verify coordinate and place_id extraction from realistic Google Maps URLs."""
    url = "https://www.google.com/maps/place/The+Taj+Mahal+Palace/@18.9217,72.8332,17z/data=!4m9!3m8!1s0x3be7d1c06fffffff:0x123456789abcdef0"

    coord_match = LAT_LNG_URL_REGEX.search(url)
    assert coord_match is not None
    assert float(coord_match.group(1)) == 18.9217
    assert float(coord_match.group(2)) == 72.8332

    id_match = PLACE_ID_HEX_REGEX.search(url)
    assert id_match is not None
    assert id_match.group(1) == "0x3be7d1c06fffffff:0x123456789abcdef0"


def test_address_components_parsing():
    """Verify city and country extraction from structured address strings."""
    extractor = DetailPageExtractor(anti_detect=AntiDetectManager(rotate_ua=False))

    full_addr = "Apollo Bunder, Colaba, Mumbai, Maharashtra 400001, India"
    city, country = extractor._parse_address_components(full_addr)
    assert country == "India"
    assert "Mumbai" in city or "Maharashtra" in city


def test_full_html_fixture_elements(fixtures_dir: Path):
    """Verify that selectors accurately identify fields in the complete fixture."""
    html_file = fixtures_dir / "hotel_detail_full.html"
    soup = BeautifulSoup(html_file.read_text(encoding="utf-8"), "lxml")

    # Name
    h1 = soup.select_one("h1.DUwDvf")
    assert h1 is not None
    assert h1.text.strip() == "The Grand Palace Hotel"

    # Category
    category_btn = soup.select_one("button[jsaction*='pane.rating.category']")
    assert category_btn is not None
    assert category_btn.text.strip() == "5-star hotel"

    # Rating
    rating_span = soup.select_one("span[aria-label*='stars']")
    assert rating_span is not None
    assert "4.7" in rating_span["aria-label"]

    # Review count
    reviews_btn = soup.select_one("button[jsaction*='pane.rating.moreReviews']")
    assert reviews_btn is not None
    match = GoogleMapsSelectors.REVIEW_COUNT.regex_pattern.search(
        reviews_btn["aria-label"]
    )
    assert match is not None
    assert int(match.group(1).replace(",", "")) == 25430

    # Address
    address_btn = soup.select_one("button[data-item-id='address']")
    assert address_btn is not None
    assert "Colaba, Mumbai" in address_btn["aria-label"]

    # Website
    website_a = soup.select_one("a[data-item-id='authority']")
    assert website_a is not None
    assert website_a["href"] == "https://www.grandpalacehotel.example.com"

    # Amenities
    amenities = [span.text.strip() for span in soup.select("div.E02Zkc span")]
    assert len(amenities) == 5
    assert "Infinity Pool" in amenities


def test_bot_detection_fixture_matches(fixtures_dir: Path):
    """Verify bot detection selectors match the captcha challenge fixture."""
    html_file = fixtures_dir / "bot_detection.html"
    soup = BeautifulSoup(html_file.read_text(encoding="utf-8"), "lxml")

    assert soup.select_one("form#captcha-form") is not None
    assert soup.select_one("div#recaptcha") is not None
