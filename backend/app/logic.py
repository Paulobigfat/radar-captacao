"""Deterministic, conservative property matching. No scraping or reverse-geocoding."""
from __future__ import annotations
import re
import unicodedata
from urllib.parse import urlsplit, urlunsplit
from pydantic import BaseModel, field_validator, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session
from .database import Building, Listing, Activity

STATUS = {"new", "verify", "prospecting", "contacted", "negotiating", "captured", "discarded"}

ALIASES = {
    "origem": "source", "fonte": "source", "id_externo": "external_id", "id_anuncio": "external_id",
    "link": "url", "anuncio_url": "url", "finalidade": "transaction", "negocio": "transaction",
    "tipo": "property_type", "tipo_imovel": "property_type", "valor": "price", "preco": "price", "aluguel": "price",
    "metragem": "area", "area_m2": "area", "dormitorios": "bedrooms", "quartos": "bedrooms",
    "vagas": "parking", "cidade": "city", "bairro": "neighborhood", "rua": "street", "logradouro": "street",
    "numero": "street_number", "numero_rua": "street_number", "edificio": "building_name", "condominio": "building_name",
    "nome_edificio": "building_name", "unidade": "unit_ref", "apartamento": "unit_ref", "cep": "postal_code",
    "latitude": "latitude", "longitude": "longitude", "situacao": "listing_status", "status_anuncio": "listing_status",
}


def normalized(value: object) -> str:
    s = unicodedata.normalize("NFKD", str(value or "").strip().lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return " ".join(s.split())


def normalize_street(value: object) -> str:
    s = normalized(value)
    s = re.sub(r"^(rua|r|avenida|av|travessa|tv|praca|pca|alameda|al)\s+", "", s)
    return s


def clean_url(value: str | None) -> str | None:
    if not value:
        return None
    p = urlsplit(value.strip())
    if p.scheme not in ("http", "https") or not p.netloc or p.username or p.password:
        raise ValueError("URL deve ser http(s), com domínio e sem credenciais")
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/") or "/", "", ""))


def normalized_number(value: str | None) -> str:
    return normalized(value).replace(" ", "")


def numeric(value):
    if value in ("", "-", None):
        return None
    if isinstance(value, (float, int)):
        return value
    s = str(value).strip().replace("R$", "").replace("m²", "").replace("m2", "").replace(" ", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    return float(s)


def clean_str(value):
    if value is None:
        return None
    val = str(value).strip()
    return val if val and val.lower() not in ("none", "null", "nan") else None


class ListingInput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    source: str = "Manual"
    external_id: str | None = None
    url: str | None = None
    transaction: str = "rent"
    property_type: str = "Apartamento"
    price: float | None = None
    area: float | None = None
    bedrooms: int | None = None
    parking: int | None = None
    city: str = ""
    neighborhood: str = ""
    street: str | None = None
    street_number: str | None = None
    building_name: str | None = None
    unit_ref: str | None = None
    postal_code: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    listing_status: str = "active"

    @field_validator("price", "area", "bedrooms", "parking", "latitude", "longitude", mode="before")
    @classmethod
    def parse_numbers(cls, v):
        return numeric(v)

    @field_validator("source", "external_id", "property_type", "city", "neighborhood", "street", "street_number", "building_name", "unit_ref", "postal_code", "listing_status", mode="before")
    @classmethod
    def parse_strings(cls, v):
        return clean_str(v)

    @field_validator("transaction", mode="before")
    @classmethod
    def parse_transaction(cls, v):
        options = {"aluguel": "rent", "locacao": "rent", "locação": "rent", "rent": "rent", "venda": "sale", "sale": "sale"}
        t = options.get(str(v or "rent").lower().strip())
        if not t:
            raise ValueError("finalidade deve ser 'rent' ou 'sale'")
        return t

    @field_validator("url")
    @classmethod
    def parse_url(cls, v):
        return clean_url(v)

    @field_validator("price", "area")
    @classmethod
    def positive_number(cls, v):
        if v is not None and (v < 0 or v > 1_000_000_000):
            raise ValueError("valor fora do intervalo aceito")
        return v

    @field_validator("bedrooms", "parking")
    @classmethod
    def positive_count(cls, v):
        if v is not None and (v < 0 or v > 100):
            raise ValueError("contagem inválida")
        return v

    @field_validator("latitude")
    @classmethod
    def valid_latitude(cls, v):
        if v is not None and not -90 <= v <= 90:
            raise ValueError("latitude inválida")
        return v

    @field_validator("longitude")
    @classmethod
    def valid_longitude(cls, v):
        if v is not None and not -180 <= v <= 180:
            raise ValueError("longitude inválida")
        return v

    @field_validator("listing_status")
    @classmethod
    def valid_status(cls, v):
        if v not in ("active", "inactive", "unknown"):
            raise ValueError("listing_status inválido")
        return v

    @field_validator("source", "external_id", "property_type", "city", "neighborhood", "street", "street_number", "building_name", "unit_ref", "postal_code")
    @classmethod
    def length_check(cls, v):
        if v and len(v) > 180:
            raise ValueError("texto muito longo")
        return v


def map_input(data: dict) -> ListingInput:
    transformed = {}
    for k, v in data.items():
        key = ALIASES.get(normalized(k).replace(" ", "_"), normalized(k).replace(" ", "_"))
        if key not in transformed or not transformed[key]:
            transformed[key] = v
    return ListingInput.model_validate(transformed)


def precision(record: ListingInput) -> str:
    if record.street and record.street_number and normalized_number(record.street_number):
        return "full"
    if record.street:
        return "partial"
    if record.neighborhood:
        return "approximate"
    return "unknown"


def building_identity(record: ListingInput):
    """Never group on street alone or neighborhood alone."""
    city = normalized(record.city)
    if not city:
        return None
    street = normalize_street(record.street)
    number = normalized_number(record.street_number)
    name = normalized(record.building_name)
    neigh = normalized(record.neighborhood)
    if street and number:
        return (f"address:{city}:{street}:{number}", 1.0, "full")
    if name and neigh:
        # Conservative matching: name+city+neighborhood may still be ambiguous.
        return (f"name:{city}:{neigh}:{name}", 0.82, "partial" if street else "approximate")
    return None


def get_existing_listing(session: Session, record: ListingInput):
    if record.external_id:
        match = session.scalar(select(Listing).where(Listing.source == record.source, Listing.external_id == record.external_id).limit(1))
        if match:
            return match
    if record.url:
        return session.scalar(select(Listing).where(Listing.url == record.url).limit(1))
    return None


def get_duplicate(session: Session, listing: Listing):
    if not listing.building_id or not listing.unit_ref:
        return None
    candidates = session.scalars(select(Listing).where(
        Listing.building_id == listing.building_id,
        Listing.transaction == listing.transaction,
        Listing.id != listing.id,
        Listing.duplicate_of.is_(None),
        Listing.unit_ref.is_not(None),
    )).all()
    for c in candidates:
        if normalized(c.unit_ref) == normalized(listing.unit_ref):
            if listing.area is not None and c.area is not None and abs(listing.area-c.area)>2:
                continue
            return c.id
    return None


def ingest(session: Session, record: ListingInput) -> dict:
    current = get_existing_listing(session, record)
    identity = building_identity(record)
    building = None
    confidence = None
    if identity:
        key, confidence, quality = identity
        building = session.scalar(select(Building).where(Building.key == key))
        if not building:
            building = Building(
                key=key, name=record.building_name, city=record.city or "",
                neighborhood=record.neighborhood or "", street=record.street,
                street_number=record.street_number, latitude=record.latitude,
                longitude=record.longitude, precision=quality, confidence=confidence,
                status="new" if confidence == 1.0 else "verify",
            )
            session.add(building)
            session.flush()
            session.add(Activity(building_id=building.id, kind="created", message="Edifício identificado a partir de anúncio importado"))
        elif confidence == 1.0 and building.precision != "full":
            building.precision = "full"
            building.confidence = 1.0
        if not building.name and record.building_name:
            building.name = record.building_name
        if not building.street and record.street:
            building.street = record.street
        if not building.street_number and record.street_number:
            building.street_number = record.street_number
        if building.latitude is None and record.latitude is not None:
            building.latitude = record.latitude
            building.longitude = record.longitude

    payload = record.model_dump()
    if current:
        # Keep existing explicitly known values when a partial update omits them.
        for key, value in payload.items():
            if value is not None and (value != "" or getattr(current, key) in (None, "")):
                setattr(current, key, value)
        if building:
            current.building_id = building.id
            current.matching_confidence = confidence
        current.precision = precision(record)
        current.duplicate_of = get_duplicate(session, current)
        session.flush()
        return {"action": "updated", "id": current.id, "building_id": current.building_id}

    listing = Listing(**payload, building_id=building.id if building else None,
                      precision=precision(record), matching_confidence=confidence)
    session.add(listing)
    session.flush()
    listing.duplicate_of = get_duplicate(session, listing)
    session.flush()
    return {"action": "created", "id": listing.id, "building_id": listing.building_id,
            "duplicate": listing.duplicate_of is not None}


def serialize_listing(l: Listing):
    fields = ("id", "building_id", "source", "external_id", "url", "transaction", "property_type",
              "price", "area", "bedrooms", "parking", "city", "neighborhood", "street",
              "street_number", "building_name", "unit_ref", "postal_code", "latitude", "longitude",
              "precision", "matching_confidence", "duplicate_of", "listing_status", "imported_at", "updated_at")
    return {k: getattr(l, k).isoformat() if isinstance(getattr(l, k), __import__("datetime").datetime) else getattr(l, k)
            for k in fields}


def serialize_building(b: Building, listings: list[Listing] | None = None):
    ll = list(b.listings) if listings is None else listings
    active = [l for l in ll if l.listing_status == "active"]
    unique = [l for l in active if not l.duplicate_of]
    prices = [l.price for l in unique if l.price is not None]
    return {
        "id": b.id, "name": b.name, "city": b.city, "neighborhood": b.neighborhood,
        "street": b.street, "street_number": b.street_number, "latitude": b.latitude,
        "longitude": b.longitude, "precision": b.precision, "confidence": b.confidence,
        "status": b.status, "notes": b.notes,
        "listings_count": len(active), "units_estimated": len(unique), "min_price": min(prices) if prices else None,
        "rent_count": sum(l.transaction == "rent" for l in unique),
        "sale_count": sum(l.transaction == "sale" for l in unique),
        "updated_at": b.updated_at.isoformat(),
    }
