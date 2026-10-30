"""Database connection management and async session provider."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.models.entities import Base

logger = structlog.get_logger(__name__)


class DatabaseManager:
    """Manages async database engine lifecycle and session dispatching."""

    def __init__(self, db_url: str, echo: bool = False):
        self.db_url = db_url
        self.echo = echo
        self._is_sqlite = db_url.startswith("sqlite")
        self._write_lock = asyncio.Lock()
        self._engine: AsyncEngine | None = None
        self._sessionmaker: async_sessionmaker[AsyncSession] | None = None

    def initialize(self) -> None:
        """Initialize the async SQLAlchemy engine."""
        connect_args = {}
        if self.db_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False

        self._engine = create_async_engine(
            self.db_url,
            echo=self.echo,
            connect_args=connect_args,
            pool_pre_ping=True,
        )

        # Optimize SQLite for concurrency if using SQLite
        if self.db_url.startswith("sqlite"):

            @event.listens_for(self._engine.sync_engine, "connect")
            def set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA busy_timeout=15000")
                cursor.close()

        self._sessionmaker = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        logger.info("database_initialized", url_scheme=self.db_url.split("://")[0])

    async def create_tables(self) -> None:
        """Create all declarative tables if not present and auto-migrate new columns."""
        if self._engine is None:
            self.initialize()
        assert self._engine is not None
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

            if self._is_sqlite:
                def migrate_sqlite_columns(sync_conn):
                    result = sync_conn.execute(text("PRAGMA table_info(hotels)"))
                    cols = [row[1] for row in result.fetchall()]
                    if cols:
                        if "source" not in cols:
                            sync_conn.execute(
                                text("ALTER TABLE hotels ADD COLUMN source VARCHAR(50) DEFAULT 'Google Maps'")
                            )
                        if "price" not in cols:
                            sync_conn.execute(
                                text("ALTER TABLE hotels ADD COLUMN price VARCHAR(50)")
                            )
                        if "source_url" not in cols:
                            sync_conn.execute(
                                text("ALTER TABLE hotels ADD COLUMN source_url TEXT")
                            )

                await conn.run_sync(migrate_sqlite_columns)
        logger.info("database_tables_verified")

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Provide an isolated async database session with automatic commit/rollback."""
        if self._sessionmaker is None:
            self.initialize()
        assert self._sessionmaker is not None

        session: AsyncSession = self._sessionmaker()
        try:
            yield session
            if self._is_sqlite:
                async with self._write_lock:
                    await session.commit()
            else:
                await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def close(self) -> None:
        """Dispose of the engine and connection pool."""
        if self._engine:
            await self._engine.dispose()
            logger.info("database_engine_disposed")
