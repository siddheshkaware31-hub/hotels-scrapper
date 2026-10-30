"""Resilient selector definitions and extraction heuristics for Google Maps.

Prefers aria-labels, data attributes, role attributes, and semantic tags over obfuscated CSS classes.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SelectorChain:
    """A prioritized list of CSS or XPath selectors with regex post-processing."""

    selectors: list[str]
    regex_pattern: re.Pattern | None = None
    attribute: str | None = None  # None indicates element textContent


class GoogleMapsSelectors:
    """Centralized resilient selectors repository."""

    # Search feed container & result items
    FEED_CONTAINER = [
        "div[role='feed']",
        "div.m6QErb[aria-label*='Results']",
        "div.m6QErb[role='region']",
    ]

    PLACE_CARD_LINKS = [
        "div[role='feed'] a[href*='/maps/place/']",
        "div[role='feed'] a.hfpxzc",
        "a[href*='/maps/place/'][aria-label]",
    ]

    END_OF_LIST_INDICATORS = [
        'span:has-text("You\'ve reached the end of the list.")',
        'p:has-text("You\'ve reached the end of the list.")',
        "div.HlvSq",
        'div:has-text("You\'ve reached the end of the list.")',
    ]

    # Bot / Captcha detection indicators
    BOT_DETECTION = [
        "form#captcha-form",
        "div#recaptcha",
        "iframe[src*='recaptcha']",
        "iframe[title*='reCAPTCHA']",
        'div:has-text("Our systems have detected unusual traffic")',
        'p:has-text("unusual traffic from your computer network")',
    ]

    # Detail view extractions
    NAME = SelectorChain(
        selectors=[
            "h1.DUwDvf",
            "div[role='main'] h1",
            "h1[class*='fontHeadlineLarge']",
            "h1",
        ]
    )

    CATEGORY = SelectorChain(
        selectors=[
            "button[jsaction*='pane.rating.category']",
            "span[class*='DkEaL']",
            "button.DkEaL",
            "button[data-item-id='address'] ~ div button",
        ]
    )

    ADDRESS = SelectorChain(
        selectors=[
            "button[data-item-id='address'] div[class*='fontBodyMedium']",
            "button[data-item-id='address']",
            "[aria-label^='Address: ']",
            "button[aria-label*='Address:']",
        ],
        attribute="aria-label",
    )

    PHONE = SelectorChain(
        selectors=[
            "button[data-item-id*='phone'] div[class*='fontBodyMedium']",
            "button[data-item-id^='phone:tel:']",
            "button[aria-label^='Phone: ']",
            "button[aria-label*='Phone:']",
        ],
        attribute="aria-label",
    )

    WEBSITE = SelectorChain(
        selectors=[
            "a[data-item-id='authority']",
            "a[aria-label^='Website: ']",
            "a[data-tooltip*='website']",
        ],
        attribute="href",
    )

    RATING = SelectorChain(
        selectors=[
            "div[role='main'] div[class*='fontDisplayLarge']",
            "span[aria-label*='stars']",
            "span.ceNzKf",
            "div[aria-label*='stars']",
        ],
        attribute="aria-label",
        regex_pattern=re.compile(r"(\d+(?:[.,]\d+)?)"),
    )

    REVIEW_COUNT = SelectorChain(
        selectors=[
            "button[jsaction*='pane.rating.moreReviews']",
            "div[role='main'] span[aria-label*='reviews']",
            "span:has-text('reviews')",
        ],
        attribute="aria-label",
        regex_pattern=re.compile(r"([\d,]+)\s*reviews?", re.IGNORECASE),
    )

    PRICE_LEVEL = SelectorChain(
        selectors=[
            "span[aria-label*='Price:']",
            "span[aria-label*='Price']",
            "span:has-text('$$$$')",
            "span:has-text('$$$')",
            "span:has-text('$$')",
            "span:has-text('$')",
            "span:has-text('₹₹₹₹')",
            "span:has-text('₹₹₹')",
            "span:has-text('₹₹')",
            "span:has-text('₹')",
        ]
    )

    CHECK_IN_INFO = SelectorChain(
        selectors=[
            "div[data-item-id*='check-in']",
            "div[aria-label*='Check-in']",
            "div[aria-label*='Hours:']",
            "button[data-item-id*='oh']",
        ],
        attribute="aria-label",
    )

    AMENITIES_CONTAINER = [
        "div[aria-label*='Amenities']",
        "div.E02Zkc",
        "div[role='region'][aria-label*='Amenities']",
        "div.bJzME",
    ]

    PHOTO_ELEMENTS = [
        "button[jsaction*='pane.heroHeaderImage'] img",
        "button[aria-label*='Photo'] img",
        "div[role='region'] img[src*='googleusercontent.com']",
        "img[src*='googleusercontent.com']",
    ]


# Regex helpers for URL coordinate & Place ID extraction
LAT_LNG_URL_REGEX = re.compile(r"/@(-?\d+\.\d+),(-?\d+\.\d+)")
PLACE_ID_HEX_REGEX = re.compile(r"!1s(0x[0-9a-fA-F]+:0x[0-9a-fA-F]+)")
PLACE_ID_CH_REGEX = re.compile(r"([0-9a-zA-Z_-]{27,})")
CID_REGEX = re.compile(r"cid=(\d+)")
