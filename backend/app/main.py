"""Local-first API. No scraping, no contact harvesting, no external network calls."""
from __future__ import annotations
import csv
import io
import json
import os
from collections import Counter
from itertools import islice
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session, selectinload
from openpyxl import Workbook, load_workbook
from .database import Base, Building, Listing, Activity, make_engine, make_session_factory
from .logic import ListingInput, STATUS, ingest, map_input, serialize_building, serialize_listing

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "static"
DEFAULT_DB = ROOT / "backend" / "data" / "radar.db"
MAX_FILE_SIZE = 5 * 1024 * 1024
MAX_ROWS = 2500


class BuildingPatch(BaseModel):
    status: str | None = None
    notes: str | None = Field(default=None, max_length=10000)
    name: str | None = Field(default=None, max_length=200)


class ActivityInput(BaseModel):
    message: str = Field(min_length=2, max_length=2000)


def create_app(database_url: str | None = None) -> FastAPI:
    if database_url is None:
        DEFAULT_DB.parent.mkdir(parents=True, exist_ok=True)
        database_url = os.environ.get("DATABASE_URL", f"sqlite:///{DEFAULT_DB.as_posix()}")
    engine = make_engine(database_url)
    Base.metadata.create_all(engine)
    SessionLocal = make_session_factory(engine)
    app = FastAPI(title="Radar de Captação", version="0.1.0", docs_url="/api/docs", redoc_url=None)
    app.state.engine = engine
    app.state.SessionLocal = SessionLocal

    def get_db():
        with SessionLocal() as session:
            yield session

    @app.get("/api/health")
    def health():
        return {"status": "ok", "service": "radar-captacao", "version": "0.1.0"}

    @app.get("/api/dashboard")
    def dashboard(db: Session = Depends(get_db)):
        listings = db.scalars(select(Listing)).all()
        buildings = db.scalars(select(Building).options(selectinload(Building.listings))).all()
        active = [l for l in listings if l.listing_status == "active"]
        distinct = [l for l in active if l.duplicate_of is None]
        neighborhoods = Counter((b.neighborhood or "Não informado") for b in buildings)
        ranked = sorted(buildings, key=lambda b: (len([l for l in b.listings if l.listing_status == "active"]), b.id), reverse=True)
        return {
            "total_listings": len(listings), "active_listings": len(active),
            "buildings": len(buildings), "unassigned": sum(l.building_id is None for l in listings),
            "for_review": sum(b.status == "verify" for b in buildings),
            "in_progress": sum(b.status in ("prospecting", "contacted", "negotiating") for b in buildings),
            "captured": sum(b.status == "captured" for b in buildings),
            "rent": sum(l.transaction == "rent" for l in distinct),
            "sale": sum(l.transaction == "sale" for l in distinct),
            "full_address": sum(l.precision == "full" for l in listings),
            "possible_duplicates": sum(l.duplicate_of is not None for l in listings),
            "neighborhoods": [{"name": name, "count": count} for name, count in neighborhoods.most_common(8)],
            "top_buildings": [serialize_building(b) for b in ranked[:6]],
        }

    @app.get("/api/meta")
    def meta(db: Session = Depends(get_db)):
        return {"cities": sorted(set(db.scalars(select(Building.city)).all()) - {""}),
                "neighborhoods": sorted(set(db.scalars(select(Building.neighborhood)).all()) - {""}),
                "statuses": sorted(STATUS)}

    @app.get("/api/buildings")
    def get_buildings(search: str = "", status: str = "", city: str = "", neighborhood: str = "",
                      transaction: str = "", precision: str = "", page: int = Query(1, ge=1),
                      limit: int = Query(20, ge=1, le=100),
                      sort: Literal["recent", "oldest", "most_listings", "name"] = "most_listings",
                      db: Session = Depends(get_db)):
        query = select(Building).options(selectinload(Building.listings))
        if search.strip():
            needle = f"%{search.strip()}%"
            query = query.where(or_(Building.name.ilike(needle), Building.street.ilike(needle),
                                     Building.neighborhood.ilike(needle), Building.city.ilike(needle)))
        if status:
            query = query.where(Building.status == status)
        if city:
            query = query.where(Building.city == city)
        if neighborhood:
            query = query.where(Building.neighborhood == neighborhood)
        if precision:
            query = query.where(Building.precision == precision)
        items = db.scalars(query).all()
        if transaction:
            items = [b for b in items if any(l.transaction == transaction and l.listing_status == "active" for l in b.listings)]
        if sort == "most_listings":
            items.sort(key=lambda b: (sum(l.listing_status == "active" for l in b.listings), b.updated_at), reverse=True)
        elif sort == "oldest":
            items.sort(key=lambda b: b.created_at)
        elif sort == "name":
            items.sort(key=lambda b: (b.name or b.street or "").lower())
        else:
            items.sort(key=lambda b: b.updated_at, reverse=True)
        total = len(items)
        return {"items": [serialize_building(b) for b in items[(page-1)*limit: page*limit]],
                "total": total, "page": page, "pages": max(1, (total+limit-1)//limit)}

    @app.get("/api/buildings/{building_id}")
    def get_building(building_id: int, db: Session = Depends(get_db)):
        b = db.scalar(select(Building).where(Building.id == building_id)
                      .options(selectinload(Building.listings), selectinload(Building.activities)))
        if not b:
            raise HTTPException(404, "Edifício não encontrado")
        return {**serialize_building(b), "listings": [serialize_listing(l) for l in sorted(b.listings, key=lambda x: x.id, reverse=True)],
                "activities": [{"id": a.id, "kind": a.kind, "message": a.message, "created_at": a.created_at.isoformat()}
                               for a in sorted(b.activities, key=lambda a: a.id, reverse=True)]}

    @app.patch("/api/buildings/{building_id}")
    def patch_building(building_id: int, data: BuildingPatch, db: Session = Depends(get_db)):
        b = db.get(Building, building_id)
        if not b:
            raise HTTPException(404, "Edifício não encontrado")
        changes = data.model_dump(exclude_unset=True)
        if "status" in changes and changes["status"] not in STATUS:
            raise HTTPException(422, "Status inválido")
        for field, value in changes.items():
            if field == "status" and value != b.status:
                db.add(Activity(building_id=b.id, kind="status", message=f"Status alterado: {b.status} → {value}"))
            setattr(b, field, value)
        db.commit()
        db.refresh(b)
        return serialize_building(b)

    @app.post("/api/buildings/{building_id}/activities", status_code=201)
    def add_activity(building_id: int, data: ActivityInput, db: Session = Depends(get_db)):
        if not db.get(Building, building_id):
            raise HTTPException(404, "Edifício não encontrado")
        activity = Activity(building_id=building_id, kind="note", message=data.message.strip())
        db.add(activity)
        db.commit()
        return {"id": activity.id, "message": activity.message}

    @app.get("/api/listings")
    def get_listings(search: str = "", transaction: str = "", precision: str = "",
                     page: int = Query(1, ge=1), limit: int = Query(25, ge=1, le=100),
                     db: Session = Depends(get_db)):
        query = select(Listing)
        if search.strip():
            needle = f"%{search.strip()}%"
            query = query.where(or_(Listing.building_name.ilike(needle), Listing.street.ilike(needle),
                                    Listing.neighborhood.ilike(needle), Listing.source.ilike(needle)))
        if transaction:
            query = query.where(Listing.transaction == transaction)
        if precision:
            query = query.where(Listing.precision == precision)
        total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
        items = db.scalars(query.order_by(Listing.imported_at.desc(), Listing.id.desc())
                           .offset((page-1)*limit).limit(limit)).all()
        return {"items": [serialize_listing(l) for l in items], "total": total,
                "page": page, "pages": max(1, (total+limit-1)//limit)}

    @app.post("/api/listings", status_code=201)
    def create_listing(data: ListingInput, db: Session = Depends(get_db)):
        try:
            result = ingest(db, data)
            db.commit()
            return result
        except Exception:
            db.rollback()
            raise

    @app.delete("/api/listings/{listing_id}")
    def delete_listing(listing_id: int, db: Session = Depends(get_db)):
        l = db.get(Listing, listing_id)
        if not l:
            raise HTTPException(404, "Anúncio não encontrado")
        # Preserve remaining duplicate relationships if a root listing is removed.
        children = db.scalars(select(Listing).where(Listing.duplicate_of == listing_id)).all()
        for c in children:
            c.duplicate_of = None
        db.delete(l)
        db.commit()
        return {"deleted": True}

    def import_rows(rows: list[dict], db: Session):
        if len(rows) > MAX_ROWS:
            raise HTTPException(413, f"Máximo de {MAX_ROWS} anúncios por importação")
        stats = {"created": 0, "updated": 0, "duplicates": 0, "errors": [], "rows": len(rows)}
        for i, data in enumerate(rows, start=2):
            try:
                if not isinstance(data, dict):
                    raise ValueError("Linha deve conter um objeto com colunas")
                entry = map_input(data)
                if not (entry.city or entry.url or entry.building_name):
                    raise ValueError("Informe cidade, edifício ou URL")
                with db.begin_nested():
                    result = ingest(db, entry)
                stats[result["action"]] += 1
                if result.get("duplicate"):
                    stats["duplicates"] += 1
            except (ValueError, ValidationError) as exc:
                if len(stats["errors"]) < 30:
                    stats["errors"].append({"row": i, "message": str(exc)[:350]})
            except Exception as exc:
                if len(stats["errors"]) < 30:
                    stats["errors"].append({"row": i, "message": f"Erro ao processar registro: {type(exc).__name__}"})
        db.commit()
        stats["failed"] = len(rows) - stats["created"] - stats["updated"]
        return stats

    @app.post("/api/import/json")
    def import_json(records: list[dict], db: Session = Depends(get_db)):
        return import_rows(records, db)

    @app.post("/api/import/file")
    async def import_file(file: UploadFile = File(...), db: Session = Depends(get_db)):
        filename = file.filename or ""
        extension = Path(filename).suffix.lower()
        if extension not in {".csv", ".xlsx", ".json"}:
            raise HTTPException(415, "Envie arquivo CSV, XLSX ou JSON")
        raw = await file.read(MAX_FILE_SIZE+1)
        if len(raw) > MAX_FILE_SIZE:
            raise HTTPException(413, "Arquivo excede 5 MB")
        try:
            if extension == ".csv":
                try:
                    content = raw.decode("utf-8-sig")
                except UnicodeDecodeError:
                    content = raw.decode("latin-1")
                dialect = csv.Sniffer().sniff(content[:4096], delimiters=",;")
                rows = list(csv.DictReader(io.StringIO(content), dialect=dialect))
            elif extension == ".json":
                rows = json.loads(raw.decode("utf-8-sig"))
                if not isinstance(rows, list):
                    raise ValueError("JSON deve conter uma lista de objetos")
            else:
                workbook = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
                sheet = workbook.active
                data = sheet.iter_rows(values_only=True)
                headers = [str(v or "").strip() for v in next(data)]
                rows = [dict(zip(headers, line)) for line in islice(data, MAX_ROWS + 1)]
                workbook.close()
        except Exception as exc:
            raise HTTPException(422, f"Não foi possível interpretar o arquivo: {str(exc)[:160]}") from exc
        return import_rows(rows, db)

    BUILDING_COLUMNS = ["id", "name", "city", "neighborhood", "street", "street_number", "precision", "confidence", "status", "listings_count", "units_estimated", "rent_count", "sale_count", "min_price", "notes"]
    LISTING_COLUMNS = ["id", "source", "external_id", "url", "transaction", "property_type", "price", "area", "bedrooms", "parking", "city", "neighborhood", "street", "street_number", "building_name", "unit_ref", "precision", "duplicate_of"]

    def safe_cell(value):
        if value is None:
            return ""
        if isinstance(value, str) and value.lstrip()[:1] in ("=", "+", "-", "@", "\t", "\r"):
            return "'" + value
        return value

    def create_export(rows, columns, file_format, basename):
        if file_format == "csv":
            out = io.StringIO()
            writer = csv.DictWriter(out, fieldnames=columns)
            writer.writeheader()
            for r in rows:
                writer.writerow({k: safe_cell(r.get(k)) for k in columns})
            body = io.BytesIO(("\ufeff"+out.getvalue()).encode("utf-8"))
            media = "text/csv; charset=utf-8"
            suffix = "csv"
        else:
            wb = Workbook()
            ws = wb.active
            ws.title = "Radar de Captação"
            ws.append(columns)
            for r in rows:
                ws.append([safe_cell(r.get(k)) for k in columns])
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
            body = io.BytesIO()
            wb.save(body)
            body.seek(0)
            media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            suffix = "xlsx"
        return StreamingResponse(body, media_type=media,
                  headers={"Content-Disposition": f'attachment; filename="{basename}.{suffix}"'})

    @app.get("/api/export/buildings")
    def export_buildings(format: Literal["csv", "xlsx"] = "xlsx", status: str = "", db: Session = Depends(get_db)):
        query = select(Building).options(selectinload(Building.listings))
        if status:
            query = query.where(Building.status == status)
        rows = [serialize_building(b) for b in db.scalars(query).all()]
        return create_export(rows, BUILDING_COLUMNS, format, "radar-edificios")

    @app.get("/api/export/listings")
    def export_listings(format: Literal["csv", "xlsx"] = "xlsx", db: Session = Depends(get_db)):
        rows = [serialize_listing(l) for l in db.scalars(select(Listing)).all()]
        return create_export(rows, LISTING_COLUMNS, format, "radar-anuncios")

    @app.get("/api/example/csv")
    def example_csv():
        return FileResponse(ROOT / "examples" / "modelo_importacao.csv", filename="modelo_importacao.csv",
                            media_type="text/csv")

    @app.get("/api/example/demo")
    def example_demo():
        return json.loads((ROOT / "examples" / "demo.json").read_text(encoding="utf-8"))

    if STATIC.exists():
        app.mount("/static", StaticFiles(directory=STATIC), name="static")

        @app.get("/", include_in_schema=False)
        def index():
            return FileResponse(STATIC / "index.html")
    return app


app = create_app()
