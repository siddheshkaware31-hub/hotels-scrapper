# Production-Grade Google Maps Hotel Data Scraper

A robust, asynchronous Python scraping engine and API consumer designed to extract comprehensive hotel metadata from Google Maps at scale. Built with **Python 3.11+**, **Playwright (async)**, **SQLAlchemy 2.0 (Async)**, **Pydantic v2**, and **structlog**.

---

## Key Features

1. **Intelligent Grid Query Generator**: Solves Google Maps' ~120-result search limit by partitioning cities into coordinate bounding-box tiles (`lat/lng` step cells) and neighborhood sub-queries.
2. **Resilient Detail Extraction**: Centralized selector engine prioritizing semantic HTML, `aria-label` attributes, and `data-*` properties over obfuscated, frequently rotating CSS classes.
3. **Pluggable Provider Architecture**: Seamlessly switch between the Playwright browser scraper (`google_maps_playwright`) and the official Google Places API (New) (`google_places_api`) without altering pipeline code.
4. **Idempotent Upsert & Deduplication**: Database storage deduplicates on Google Place ID / hex CID. Reruns update existing records without creating duplicates.
5. **Crash-Resistant Resume**: Job runs and individual place tasks are tracked in the database (`PENDING`, `COMPLETED`, `FAILED`). Crashed or paused runs resume from the exact stopping point.
6. **Anti-Bot & Politeness Defenses**:
   - Randomized jitter delays between interactions.
   - Concurrency limits via `asyncio.Semaphore`.
   - Automatic CAPTCHA and "unusual traffic" detection: halts worker, cools down, logs alerts, and **does not attempt to solve CAPTCHAs**.
   - User-Agent rotation and lightweight stealth evasions.
   - Automatic snapshot capture (HTML + screenshot) on parsing failures for debugging.
7. **Swappable Storage**: Async SQLite by default, seamlessly switchable to PostgreSQL via connection string.
8. **Export Service**: Stream database records directly into CSV or JSON.

---

## Extracted Fields

| Field | Description | Example |
| :--- | :--- | :--- |
| `place_id` | Unique Google Maps Place ID or CID hex | `0x3be7d1c06fffffff:0x123456789abcdef0` |
| `name` | Establishment title | `The Taj Mahal Palace, Mumbai` |
| `category` | Primary category | `5-star hotel` |
| `full_address` | Street address string | `Apollo Bunder, Colaba, Mumbai, Maharashtra 400001, India` |
| `city` | Inferred or configured city | `Mumbai` |
| `country` | Inferred or configured country | `India` |
| `latitude` | Geographic coordinate | `18.9217` |
| `longitude` | Geographic coordinate | `72.8332` |
| `phone` | Contact telephone number | `+91 22 6665 3366` |
| `website` | Official website URL | `https://www.tajhotels.com/...` |
| `rating` | Average customer score | `4.7` |
| `review_count` | Total review count | `25430` |
| `price_level` | Cost tier indicator | `$$$$` |
| `check_in_info` | Opening hours / Check-in schedule | `Check-in: 2:00 PM / Check-out: 12:00 PM` |
| `amenities` | Extracted amenity tags | `["Free Wi-Fi", "Infinity Pool", "Spa"]` |
| `photo_urls` | First 5 high-resolution photos | `["https://lh5.googleusercontent.com/..."]` |
| `google_maps_url` | Full permalink | `https://www.google.com/maps/place/...` |
| `scraped_at` | UTC timestamp of extraction | `2026-10-30T17:00:00Z` |

---

## Project Structure

```text
hotel_scraper/
├── config/
│   ├── config.yaml          # Regions, grid sizes, timeouts, and anti-bot rules
│   └── logging.py           # structlog JSON and Console loggers
├── src/
│   ├── cli.py               # Typer CLI entrypoint
│   ├── config.py            # Pydantic Settings & YAML loader
│   ├── models/
│   │   ├── schemas.py       # Pydantic models (HotelData, JobState)
│   │   └── entities.py      # SQLAlchemy 2.0 ORM tables (Hotel, JobRun, ScrapingTask)
│   ├── db/
│   │   ├── session.py       # Async engine & connection pool (SQLite / Postgres)
│   │   └── repository.py    # Idempotent upserts, task queries, resume state
│   ├── providers/
│   │   ├── base.py          # Abstract BaseHotelProvider contract
│   │   ├── google_maps/     # Playwright scraper (selectors, search, detail, browser)
│   │   └── google_places_api/ # Google Places API (New) provider
│   ├── pipeline/
│   │   ├── grid.py          # Bounding box coordinate grid generator
│   │   ├── runner.py        # Worker loop, retry backoff, concurrency dispatcher
│   │   └── exporter.py      # CSV / JSON export engine
│   └── utils/
│       ├── backoff.py       # Decorrelated exponential backoff with full jitter
│       └── snapshot.py      # HTML/screenshot failure snapshot persistence
├── snapshots/               # Raw HTML snapshots of extraction failures
├── data/                    # SQLite database and CSV/JSON export files
├── tests/                   # Pytest test suite with HTML fixtures
├── Dockerfile               # Production container image
├── docker-compose.yml       # Scraper and optional PostgreSQL services
├── requirements.txt         # Production dependencies
└── README.md
```

---

## Installation & Setup

### 1. Prerequisites
- Python 3.11 or higher
- Git

### 2. Virtual Environment Setup
```bash
# Clone the repository
git clone <repo_url>
cd splendid-kepler

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt -r requirements-dev.txt

# Install Playwright browser dependencies
playwright install chromium
```

### 3. Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Key configuration overrides in `.env`:
- `DATABASE_URL`: Defaults to `sqlite+aiosqlite:///data/hotels.db`. For PostgreSQL, set `postgresql+asyncpg://user:password@localhost:5432/hotel_db`.
- `SCRAPER_HEADLESS`: `true` for background runs, `false` to view the browser window during testing.
- `SCRAPER_CONCURRENCY`: Number of concurrent browser worker tasks (recommended: 2–3 for single IP).
- `GOOGLE_PLACES_API_KEY`: API key if utilizing the `google_places_api` provider.

---

## Usage Guide (CLI)

The CLI is powered by `typer` and provides four primary commands:

### 1. Scrape a Region
```bash
# Scrape hotels in Mumbai (using bounding-box grid defined in config.yaml)
python -m src.cli scrape --region "Mumbai"

# Scrape with visible browser and custom concurrency
python -m src.cli scrape --region "Mumbai" --no-headless --concurrency 1

# Scrape using the official Google Places API provider
python -m src.cli scrape --region "Mumbai" --provider "google_places_api"
```

### 2. Resume an Interrupted Job
If a run was stopped (via `Ctrl+C`, network failure, or CAPTCHA trigger), simply run:
```bash
# Automatically finds and resumes the latest incomplete job
python -m src.cli resume

# Resume a specific job ID
python -m src.cli resume --job-id "job_mumbai_a1b2c3d4"
```

### 3. Export Collected Data
```bash
# Export all hotels to CSV (saved to data/exports/hotels_all_<timestamp>.csv)
python -m src.cli export --format csv

# Export Mumbai hotels to JSON
python -m src.cli export --format json --city "Mumbai"

# Custom output destination
python -m src.cli export --format csv --output "./output.csv"
```

### 4. Inspect System Status
```bash
python -m src.cli status
```

---

## Docker Deployment

### Run via Docker Compose
```bash
# Build and run the scraper container
docker compose build
docker compose up
```

### Run Custom Command in Container
```bash
docker compose run --rm scraper export --format csv
```

---

## Running Unit Tests

The test suite validates selector resilience, parser behavior against saved HTML fixtures, bounding box cell math, database upserting, and provider contract adherence:

```bash
pytest -v
```

---

## Troubleshooting Guide

### 1. CAPTCHA / Unusual Traffic Triggered
- **Symptoms**: Log outputs `CRITICAL: Google redirected to /sorry/index CAPTCHA page` or `anti_bot_alert_captcha_cooldown_initiated`.
- **System Behavior**: The scraper will **never** attempt to solve the CAPTCHA. It halts that worker, saves a snapshot to `snapshots/`, and triggers a cooldown period (default: 180 seconds).
- **Remediation**:
  1. Increase `min_delay_sec` and `max_delay_sec` in `config/config.yaml`.
  2. Reduce `concurrency` from 3 to 1 or 2.
  3. Configure a residential proxy pool in `config/config.yaml` or `.env`.

### 2. Missing Selectors / Stale Data
- **Symptoms**: Certain fields (e.g. amenities or price level) are `null` in DB.
- **System Behavior**: Individual field failures log a warning and default to `null` to prevent crashing the entire run. If a critical failure occurs, a full HTML dump is saved in `snapshots/`.
- **Remediation**: Inspect `snapshots/failure_<id>.html` to check if Google has updated DOM element attributes. Update selectors in [selectors.py](file:///c:/Users/ASUS/Documents/antigravity/splendid-kepler/src/providers/google_maps/selectors.py).

### 3. Google Consent Interstitial (EU / EEA)
- The browser manager automatically detects and clicks European consent buttons (`"Accept all"`, `"I agree"`). If a new consent modal variant appears, add its selector to `_dismiss_consent()` in `src/providers/google_maps/browser.py`.

---

## Known Limitations & Google Terms of Service (ToS) Risks

### 1. Google Terms of Service (ToS) Considerations
- **Section 3.2.3 of Google Maps/Google Earth Additional Terms of Service**: Explicitly prohibits extracting, mass downloading, scraping, or creating derivative works of Google Maps content outside the official Google Maps Platform APIs.
- **Risk of IP Blacklisting**: Frequent, non-human automated requests from non-residential IP ranges (e.g., AWS, GCP, DigitalOcean) are quickly identified and throttled by Google with 429/interstitial CAPTCHA blocks.
- **Legal Compliance**: This software is intended for legitimate data engineering research, staging, and API migration testing. For enterprise production pipelines where legal compliance is mandatory, use the included `google_places_api` provider with an official API key.

### 2. Technical Limitations of Google Maps Web UI
- **120-Result Search Cap**: A single Google Maps search feed never returns more than approximately 120 results, regardless of how much you scroll. The Grid Query Generator mitigates this by tiling the bounding box into smaller coordinate grids, but extremely dense areas (e.g., Times Square, Tokyo Station) may still hit the cap unless tile size is decreased to < 1.0 km.
- **Dynamic CSS Obfuscation**: Class names (like `.DUwDvf` or `.hfpxzc`) are generated by Google's build pipelines and can change without notice. While this codebase mitigates this by targeting semantic `aria-label`, `data-item-id`, and structural tags, periodic selector maintenance is unavoidable.
- **Photo CDN Ephemerality**: Scraped photo URLs from `googleusercontent.com` frequently carry time-limited HMAC authentication tokens and may expire after several days or weeks. Permanent asset storage requires downloading image binaries to an S3/GCS bucket at scrape time.
- **Amenities Inconsistency**: Google Maps displays hotel amenities inconsistently; some hotels only expose amenities behind an interactive "About" modal tab or booking engine iframe.
