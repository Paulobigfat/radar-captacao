"""Feeds locais/HTTPS e varredura cautelosa de HTML público sem contornar barreiras."""
from __future__ import annotations

import csv
import io
import ipaddress
import json
import os
import socket
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import DataSource, SourceRun, utcnow

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 2500


class SourceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    kind: str
    location: str = Field(min_length=1, max_length=2048)
    interval_minutes: int = Field(default=360, ge=15, le=10080)
    enabled: bool = True
    rights_confirmed: bool = False

    @field_validator("name")
    @classmethod
    def source_name(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def valid(self):
        if self.kind in ("file", "https") and not self.rights_confirmed:
            raise ValueError("Confirme que o feed ou arquivo foi disponibilizado para este uso")
        if self.kind == "file":
            self.location = validate_filename(self.location)
        elif self.kind == "https":
            validate_feed_url(self.location)
        elif self.kind == "web":
            validate_feed_url(self.location)
        else:
            raise ValueError("Tipos permitidos: file, https ou web")
        return self


class SourcePatch(BaseModel):
    enabled: bool | None = None
    interval_minutes: int | None = Field(default=None, ge=15, le=10080)


def validate_filename(value: str) -> str:
    filename = value.strip()
    if filename != Path(filename).name or '/' in filename or '\\' in filename or filename in ('.', '..'):
        raise ValueError("Informe somente o nome de um arquivo dentro da pasta imports/")
    if Path(filename).suffix.lower() not in {'.csv', '.json'}:
        raise ValueError("Arquivo deve ser CSV ou JSON")
    return filename


def validate_feed_url(value: str) -> None:
    parsed = urlsplit(value)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Informe uma URL HTTPS válida sem credenciais embutidas")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Porta inválida") from exc
    if port not in (None, 443):
        raise ValueError("A fonte HTTPS deve usar a porta 443")
    host = parsed.hostname
    if host == 'localhost' or host.endswith('.localhost') or host.endswith('.local'):
        raise ValueError("Endereço local ou privado não permitido")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return
    if not ip.is_global:
        raise ValueError("Endereço local ou privado não permitido")


def public_address_only(hostname: str) -> None:
    """Reject non-public addresses before making an outbound HTTP request."""
    try:
        addresses = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("Não foi possível resolver o domínio da fonte") from exc
    if not addresses or any(not ipaddress.ip_address(info[4][0]).is_global for info in addresses):
        raise ValueError("A fonte aponta para endereço de rede privado ou reservado")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Redirecionamentos HTTP não são aceitos para fontes automáticas")


def read_source(source: DataSource, imports_dir: Path) -> bytes:
    if source.kind == 'file':
        filename = validate_filename(source.location)
        imports = imports_dir.resolve()
        target = (imports / filename).resolve()
        if target.parent != imports or not target.is_file():
            raise ValueError("Arquivo não encontrado na pasta imports/")
        if target.stat().st_size > MAX_BYTES:
            raise ValueError("Arquivo acima do limite de 5 MB")
        return target.read_bytes()

    validate_feed_url(source.location)
    host = urlsplit(source.location).hostname
    public_address_only(host)
    request = urllib.request.Request(source.location, headers={
        'User-Agent': 'RadarCaptacao/0.2 (+approved-feed-import)',
        'Accept': 'application/json,text/csv,text/plain',
    })
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(request, timeout=8) as response:
            body = response.read(MAX_BYTES + 1)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ValueError(f"Não foi possível consultar a fonte: {type(exc).__name__}") from exc
    if len(body) > MAX_BYTES:
        raise ValueError("Fonte excede o limite de 5 MB")
    return body


def parse_feed(content: bytes, location: str) -> list[dict]:
    if not content.strip():
        raise ValueError("Fonte vazia")
    try:
        decoded = content.decode('utf-8-sig')
    except UnicodeDecodeError:
        decoded = content.decode('latin-1')
    kind = '.json' if location.lower().split('?')[0].endswith('.json') else '.csv' if location.lower().split('?')[0].endswith('.csv') else ''
    if kind == '.json' or (not kind and decoded.lstrip().startswith(('[', '{'))):
        try:
            data = json.loads(decoded)
        except json.JSONDecodeError as exc:
            raise ValueError("JSON inválido") from exc
        if isinstance(data, dict):
            data = data.get('items')
        if not isinstance(data, list):
            raise ValueError("JSON deve ser uma lista ou objeto com campo items em lista")
        rows = data
    else:
        try:
            delimiter = csv.Sniffer().sniff(decoded[:4096], delimiters=',;').delimiter
        except csv.Error:
            delimiter = ';' if decoded.splitlines()[0].count(';') > decoded.splitlines()[0].count(',') else ','
        rows = list(csv.DictReader(io.StringIO(decoded), delimiter=delimiter))
    if not rows:
        raise ValueError("Fonte sem registros; nenhum anúncio foi alterado")
    if len(rows) > MAX_ROWS:
        raise ValueError(f"Fonte acima de {MAX_ROWS} registros")
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError("Cada anúncio precisa ser um objeto com campos nomeados")
    return rows


def source_to_dict(source: DataSource) -> dict:
    return {
        'id': source.id, 'name': source.name, 'kind': source.kind,
        'location': source.location, 'interval_minutes': source.interval_minutes,
        'enabled': source.enabled, 'rights_confirmed': source.rights_confirmed,
        'last_run_at': source.last_run_at.isoformat() if source.last_run_at else None,
        'last_result': source.last_result, 'last_error': source.last_error,
        'created_at': source.created_at.isoformat(),
    }


def run_to_dict(run: SourceRun) -> dict:
    return {
        'id': run.id, 'source_id': run.source_id, 'started_at': run.started_at.isoformat(),
        'finished_at': run.finished_at.isoformat() if run.finished_at else None,
        'status': run.status, 'created': run.created, 'updated': run.updated,
        'failed': run.failed, 'message': run.message,
    }


def execute_source(db: Session, source: DataSource, imports_dir: Path, importer) -> dict:
    """Run one import, preserving existing listings if fetching or parsing fails.

    The caller serializes concurrent runs using an app-level lock.
    """
    now = utcnow()
    run = SourceRun(source_id=source.id, started_at=now, status='running',
                    message='Consulta iniciada. Lendo páginas públicas e verificando anúncios...')
    db.add(run)
    # This commit makes an in-progress scan visible to the UI while the worker
    # is running. Previously it was invisible until completion.
    db.commit()
    run_id = run.id
    try:
        scan_info = None
        if source.kind == 'web':
            from .crawler import crawl_public_site
            rows, scan_info = crawl_public_site(source.location)
        else:
            rows = parse_feed(read_source(source, imports_dir), source.location)
        # Stable identifiers make recurring imports idempotent; otherwise re-running
        # an incomplete feed could create duplicate listings every interval.
        accepted = []
        for i, data in enumerate(rows):
            if not (data.get('external_id') or data.get('id_externo') or data.get('id_anuncio') or
                    data.get('url') or data.get('link') or data.get('anuncio_url')):
                raise ValueError(f"Registro {i + 1} sem id_externo ou URL; a fonte não pode ser sincronizada com segurança")
            accepted.append({**data, 'source': source.name, 'origem': source.name, 'fonte': source.name})
        stats = importer(accepted, db)
        run.status = 'ok' if stats['failed'] == 0 else 'partial'
        run.created = stats['created']
        run.updated = stats['updated']
        run.failed = stats['failed']
        run.message = f"{stats['created']} novos, {stats['updated']} atualizados, {stats['failed']} inválidos"
        if scan_info is not None:
            run.message = (f"{scan_info['pages']} páginas analisadas, {scan_info['extracted']} anúncios identificados; "
                           + run.message)
            if not rows:
                run.status = 'partial'
                details = scan_info.get('reasons', {})
                run.message += (f"; nenhum anúncio compatível reconhecido. "
                                f"Páginas sem dados compatíveis: {details.get('not_listing', 0)}; "
                                f"bloqueadas pelo robots.txt: {scan_info.get('blocked', 0)}; "
                                f"falhas de leitura: {len(scan_info.get('errors', []))}. "
                                "O site pode usar JavaScript ou formato ainda não suportado.")
            if scan_info.get('errors'):
                run.message += '; Exemplos de erros: '+', '.join(scan_info['errors'][:2])
        run.message = run.message[:480]
        source.last_error = run.message if run.status != 'ok' else None
        source.last_result = run.status
    except Exception as exc:
        db.rollback()
        # Reuse the persisted running record; don't leave a phantom running
        # entry and add a second error record for one attempted scan.
        source = db.get(DataSource, source.id)
        run = db.get(SourceRun, run_id)
        run.status = 'error'
        run.message = str(exc)[:480]
        source.last_error = str(exc)[:400]
        source.last_result = 'error'
    source.last_run_at = utcnow()
    run.finished_at = utcnow()
    db.commit()
    return run_to_dict(run)


def due_sources(db: Session) -> list[DataSource]:
    now = utcnow()
    sources = db.scalars(select(DataSource).where(DataSource.enabled.is_(True))).all()
    return [s for s in sources if s.last_run_at is None or now - s.last_run_at >= timedelta(minutes=s.interval_minutes)]
