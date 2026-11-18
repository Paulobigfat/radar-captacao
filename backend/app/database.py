"""SQLite persistence for the single-user local MVP."""
from datetime import datetime, timezone
from sqlalchemy import create_engine, ForeignKey, String, DateTime, Integer, Float, Text, UniqueConstraint, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker
from sqlalchemy.pool import StaticPool


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Building(Base):
    __tablename__ = "buildings"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(500), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str] = mapped_column(String(120), default="")
    neighborhood: Mapped[str] = mapped_column(String(120), default="")
    street: Mapped[str | None] = mapped_column(String(180))
    street_number: Mapped[str | None] = mapped_column(String(30))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    precision: Mapped[str] = mapped_column(String(30), default="approximate")
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    status: Mapped[str] = mapped_column(String(30), default="new")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    listings: Mapped[list["Listing"]] = relationship(back_populates="building")
    activities: Mapped[list["Activity"]] = relationship(back_populates="building", cascade="all, delete-orphan")


class Listing(Base):
    __tablename__ = "listings"
    id: Mapped[int] = mapped_column(primary_key=True)
    building_id: Mapped[int | None] = mapped_column(ForeignKey("buildings.id"), index=True)
    source: Mapped[str] = mapped_column(String(100), default="Manual")
    external_id: Mapped[str | None] = mapped_column(String(150))
    url: Mapped[str | None] = mapped_column(Text)
    transaction: Mapped[str] = mapped_column(String(20), default="rent")
    property_type: Mapped[str] = mapped_column(String(60), default="Apartamento")
    price: Mapped[float | None] = mapped_column(Float)
    area: Mapped[float | None] = mapped_column(Float)
    bedrooms: Mapped[int | None] = mapped_column(Integer)
    parking: Mapped[int | None] = mapped_column(Integer)
    city: Mapped[str] = mapped_column(String(120), default="")
    neighborhood: Mapped[str] = mapped_column(String(120), default="")
    street: Mapped[str | None] = mapped_column(String(180))
    street_number: Mapped[str | None] = mapped_column(String(30))
    building_name: Mapped[str | None] = mapped_column(String(200))
    unit_ref: Mapped[str | None] = mapped_column(String(60))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    precision: Mapped[str] = mapped_column(String(30), default="unknown")
    matching_confidence: Mapped[float | None] = mapped_column(Float)
    duplicate_of: Mapped[int | None] = mapped_column(ForeignKey("listings.id"), index=True)
    listing_status: Mapped[str] = mapped_column(String(30), default="active")
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    building: Mapped[Building | None] = relationship(back_populates="listings")
    __table_args__ = (
        Index("ix_listings_source_external_id", "source", "external_id"),
        Index("ix_listings_city_neighborhood", "city", "neighborhood"),
    )


class DataSource(Base):
    __tablename__ = "data_sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    kind: Mapped[str] = mapped_column(String(20))
    location: Mapped[str] = mapped_column(Text)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=360)
    enabled: Mapped[bool] = mapped_column(default=True)
    rights_confirmed: Mapped[bool] = mapped_column(default=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_result: Mapped[str | None] = mapped_column(String(20))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    runs: Mapped[list["SourceRun"]] = relationship(back_populates="source", cascade="all, delete-orphan")


class SourceRun(Base):
    __tablename__ = "source_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="running")
    created: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(String(500), default="")
    source: Mapped[DataSource] = relationship(back_populates="runs")


class Activity(Base):
    __tablename__ = "activities"
    id: Mapped[int] = mapped_column(primary_key=True)
    building_id: Mapped[int] = mapped_column(ForeignKey("buildings.id"), index=True)
    kind: Mapped[str] = mapped_column(String(35), default="note")
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    building: Mapped[Building] = relationship(back_populates="activities")


def make_engine(url: str):
    args = {"connect_args": {"check_same_thread": False}}
    if url in ("sqlite://", "sqlite:///:memory:"):
        args["poolclass"] = StaticPool
    engine = create_engine(url, **args, future=True)
    if url.startswith("sqlite"):
        from sqlalchemy import event
        @event.listens_for(engine, "connect")
        def foreign_keys(dbapi_connection, _):
            cur = dbapi_connection.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()
    return engine


def make_session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
