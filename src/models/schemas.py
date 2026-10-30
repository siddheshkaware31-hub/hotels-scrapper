"""Pydantic schemas for data validation and pipeline serialization."""

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ExportFormat(str, Enum):
    CSV = "csv"
    JSON = "json"


class JobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PAUSED = "PAUSED"


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class HotelCandidate(BaseModel):
    """Initial search result candidate prior to detail extraction."""

    google_maps_url: str
    area_query: str
    place_id: str | None = None
    name_hint: str | None = None
    source: str = "Google Maps"


class HotelData(BaseModel):
    """Canonical model for scraped hotel details."""

    place_id: str = Field(description="Unique Google Maps Place ID, provider hash, or CID hex")
    name: str = Field(description="Hotel title or establishment name")
    category: str | None = Field(default="Hotel", description="Primary category tag")
    source: str = Field(
        default="Google Maps",
        description="Data source provider e.g. Google Maps, Justdial, MakeMyTrip, Booking.com",
    )
    price: str | None = Field(
        default=None, description="Nightly price string e.g. ₹1,738 or price per night"
    )
    source_url: str | None = Field(
        default=None, description="Direct URL on the source platform"
    )
    full_address: str | None = Field(
        default=None, description="Full street address string"
    )
    city: str | None = Field(default=None, description="Inferred or parsed city")
    country: str | None = Field(default=None, description="Inferred or parsed country")
    latitude: float | None = Field(
        default=None, description="Geographic latitude coordinate"
    )
    longitude: float | None = Field(
        default=None, description="Geographic longitude coordinate"
    )
    phone: str | None = Field(default=None, description="Normalized contact telephone")
    website: str | None = Field(default=None, description="Official hotel website URL")
    rating: float | None = Field(
        default=None, ge=1.0, le=5.0, description="Average review score"
    )
    review_count: int | None = Field(
        default=None, ge=0, description="Total number of customer reviews"
    )
    price_level: str | None = Field(
        default=None, description="Price tier indicator e.g. $, $$, $$$"
    )
    check_in_info: str | None = Field(
        default=None, description="Check-in/check-out schedule or opening hours"
    )
    amenities: list[str] = Field(
        default_factory=list, description="Extracted hotel amenities/features"
    )
    photo_urls: list[str] = Field(
        default_factory=list, description="Top photo image URLs (up to 5)"
    )
    google_maps_url: str = Field(description="Full Google Maps destination permalink")
    scraped_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp of extraction",
    )

    @field_validator("photo_urls")
    @classmethod
    def cap_photos(cls, v: list[str]) -> list[str]:
        """Ensure at most 5 photo URLs are retained."""
        return v[:5] if v else []

    @field_validator("rating")
    @classmethod
    def round_rating(cls, v: float | None) -> float | None:
        return round(v, 1) if v is not None else None

    model_config = ConfigDict(from_attributes=True)


class JobState(BaseModel):
    """Job progress snapshot used for observability and resume commands."""

    job_id: str
    region: str
    status: JobStatus
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    started_at: datetime
    finished_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
