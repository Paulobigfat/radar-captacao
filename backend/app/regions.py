"""Configuração editorial das zonas; nunca infere zona pela posição aproximada."""
import json
import unicodedata
from pathlib import Path
from functools import lru_cache

ROOT = Path(__file__).resolve().parents[2]


def norm(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(text or '').casefold())
                   if not unicodedata.combining(c)).strip()


@lru_cache(maxsize=1)
def zone_map():
    path = ROOT / 'config' / 'zonas.json'
    if not path.is_file():
        return {}
    mapping = json.loads(path.read_text(encoding='utf-8')).get('cidades', {})
    return {(norm(city), norm(bairro)): zone
            for city, zones in mapping.items()
            for zone, bairros in zones.items()
            for bairro in bairros}


def zone_for(city: str | None, neighborhood: str | None) -> str:
    if not city or not neighborhood:
        return 'Não classificada'
    return zone_map().get((norm(city), norm(neighborhood)), 'Não classificada')
