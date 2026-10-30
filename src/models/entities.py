"""SQLAlchemy 2.0 ORM entities for SQLite / PostgreSQL."""

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Hotel(Base):
    """Database model for storing hotel properties, deduplicated by place_id."""

    __tablename__ = "hotels"

    place_id: Mapped[str] = mapped_column(String(128), primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source: Mapped[str] = mapped_column(
        String(50), default="Google Maps", nullable=False, index=True
    )
    price: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    full_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(60), nullable=True)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    review_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    check_in_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    amenities: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    photo_urls: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    google_maps_url: Mapped[str] = mapped_column(Text, nullable=False)
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (Index("idx_hotels_city_rating", "city", "rating"),)


class JobRun(Base):
    """Persistent job execution record for progress tracking and resume."""

    __tablename__ = "job_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    region: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="RUNNING", index=True
    )
    total_candidates: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    tasks: Mapped[list["ScrapingTask"]] = relationship(
        "ScrapingTask", back_populates="job_run", cascade="all, delete-orphan"
    )


class ScrapingTask(Base):
    """Granular detail scraping task unit to guarantee atomic progress persistence."""

    __tablename__ = "scraping_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("job_runs.id"), nullable=False, index=True
    )
    place_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    google_maps_url: Mapped[str] = mapped_column(Text, nullable=False)
    area_query: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING", index=True
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    job_run: Mapped["JobRun"] = relationship("JobRun", back_populates="tasks")

    __table_args__ = (Index("idx_tasks_job_status", "job_run_id", "status"),)
