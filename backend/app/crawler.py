"""Varredura conservadora de páginas imobiliárias públicas.

Sem login, APIs privadas, contorno de bloqueios, ocultação de endereço ou dados de contato.
Respeita robots.txt e limita domínio, volume, tamanho e tempo das requisições.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import socket
import time
import urllib.error
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET
from collections import deque
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit, unquote

from .sources import validate_feed_url, public_address_only

USER_AGENT = "RadarCaptacaoPesquisa/0.3 (+coleta-publica-respeitando-robots)"
MAX_PAGES = 24
MAX_CANDIDATES = 200
MAX_HTML_BYTES = 1_000_000
MAX_SITEMAP_BYTES = 1_000_000
MIN_DELAY_SECONDS = 0.75
LISTING_HINT = re.compile(r"(?:im[oó]ve[il]|apartament|casa|sobrado|kitnet|studio|loft|flat|terreno|alug|loca|venda|property|listing|detalh|an[uú]ncio|ficha|oferta)", re.I)
DETAIL_HINT = re.compile(r"(?:/(?:imovel|imoveis|detalhes|detalhe|anuncio|property|listing|ficha|oferta)/[^/?]+|(?:apartamento|casa|terreno|sobrado|studio)[^/]*[-/](?:\d{3,}|[a-z\d-]+[-/]\d{3,}))", re.I)
INDEX_PATH = re.compile(r"/(?:imoveis|apartamentos|casas|aluguel|locacao|venda|comprar|alugar|buscar|busca|pesquisa|catalogo|lista)$", re.I)
TRANSACTION_RENT = re.compile(r"\b(?:aluguel|alugar|alugu[eé]is|loca[çc][aã]o|locar|para\s+alugar|rent|rental)\b", re.I)
TRANSACTION_SALE = re.compile(r"\b(?:venda|vender|comprar|compra|[àa]\s+venda|sale|for\s+sale)\b", re.I)
PAGINATION_KEYS = {'page', 'pagina', 'p', 'pg', 'id', 'codigo', 'cod', 'ref', 'imovel', 'offset'}
BAD_HINT = re.compile(r"(?:^|/)(?:login|entrar|cadastro|contato|blog|noticias|politica|privacidade|termos|admin|api|whatsapp|carrinho|favoritos|user)(?:/|$)", re.I)
MONEY_RE = re.compile(r"R\$\s*([\d.]+(?:,\d{2})?)", re.I)
STREET_RE = re.compile(r"\b((?:Rua|R\.|Avenida|Av\.|Travessa|Alameda|Praça|Estrada)\s+[^\n,|]{4,75}?)(?:\s*,\s*|\s+[nN][º°o.]?\s*)(\d{1,6}[A-Za-z]?)(?=\b|$)", re.I)
STREET_ONLY_RE = re.compile(r"\b((?:Rua|R\.|Avenida|Av\.|Travessa|Alameda|Praça|Estrada)\s+[\wÀ-ÿ.'-]+(?:\s+[\wÀ-ÿ.'-]+){0,8})", re.I)
AREA_RE = re.compile(r"\b(\d{1,5}(?:[,\.]\d{1,2})?)\s*m[²2]\b", re.I)
BEDS_RE = re.compile(r"\b([1-9])\s*(?:quartos?|dormit[oó]rios?)\b", re.I)
ADDRESS_LABEL_RE = re.compile(r"\b(?:bairro|localiza[çc][aã]o)\s*:[ \t]*([^\n|;,]{3,60})", re.I)
CITY_LABEL_RE = re.compile(r"\b(?:cidade|munic[ií]pio)\s*:[ \t]*([^\n|;,]{3,60})", re.I)


class ScanError(ValueError):
    """Reason a website could not be scanned safely."""


class StrictRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old, new = urlsplit(req.full_url), urlsplit(newurl)
        # A redirect to a different host, HTTP, or non-standard port must not
        # be followed. Same-host canonical paths and trailing slash are common.
        if (new.scheme != 'https' or new.hostname != old.hostname or
                new.port not in (None, 443) or new.username or new.password):
            raise ScanError("Redirecionamento externo ou inseguro. Informe a URL HTTPS final (com www, se necessário).")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _domain(url: str):
    validate_feed_url(url)
    return urlsplit(url).hostname.lower()


def _safe_link(url: str, base: str, domain: str) -> str | None:
    try:
        full = urljoin(base, url)
        p = urlsplit(full)
        if p.scheme != "https" or p.hostname != domain or p.username or p.password:
            return None
        if p.port not in (None, 443):
            return None
        if BAD_HINT.search(p.path):
            return None
        # Keep explicit page numbers / listing IDs, but drop tracking/session
        # parameters. Discarding *all* queries hid paginated inventory.
        query = urlencode([(k, v) for k, v in parse_qsl(p.query, keep_blank_values=False)
                           if k.lower() in PAGINATION_KEYS][:5])
        return urlunsplit(("https", p.netloc.lower(), p.path or "/", query, ""))
    except (ValueError, AttributeError):
        return None


def _fetch(url: str, domain: str, max_bytes: int = MAX_HTML_BYTES) -> tuple[bytes, str]:
    if _safe_link(url, url, domain) is None:
        raise ScanError("Endereço fora do domínio cadastrado ou URL não permitida")
    public_address_only(domain)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept": "text/html,application/xml,text/xml,text/plain,*/*;q=0.2"})
    try:
        with urllib.request.build_opener(StrictRedirect).open(req, timeout=8) as res:
            content_type = res.headers.get("Content-Type", "").lower()
            if not any(t in content_type for t in ("text/html", "xml", "text/plain")):
                raise ScanError("Resposta não é HTML/XML público")
            content = res.read(max_bytes + 1)
            if len(content) > max_bytes:
                raise ScanError("Página excede o limite de tamanho")
            return content, content_type
    except urllib.error.HTTPError as err:
        if err.code == 404:
            raise FileNotFoundError(url) from err
        raise ScanError(f"Site respondeu HTTP {err.code} ao consultar uma página pública") from err
    except (urllib.error.URLError, TimeoutError, OSError) as err:
        raise ScanError(f"Falha de rede ({type(err).__name__})") from err


def _robots(seed_url: str, domain: str) -> tuple[urllib.robotparser.RobotFileParser, list[str], float]:
    url = f"https://{domain}/robots.txt"
    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(url)
    sitemaps = []
    try:
        body, _ = _fetch(url, domain, 200_000)
        lines = body.decode("utf-8-sig", "replace").splitlines()
        parser.parse(lines)
        for line in lines:
            if line.lower().startswith("sitemap:"):
                candidate = _safe_link(line.split(":", 1)[1].strip(), url, domain)
                if candidate and len(sitemaps) < 3:
                    sitemaps.append(candidate)
    except FileNotFoundError:
        parser.parse([])  # robots.txt ausente (HTTP 404) não estabelece restrições.
    except (ValueError, ScanError) as exc:
        raise ScanError(f"Não foi possível verificar robots.txt com segurança: {exc}") from exc
    if not parser.can_fetch(USER_AGENT, seed_url):
        raise ScanError("robots.txt não permite visitar essa URL. Fonte não será varrida.")
    delay = parser.crawl_delay(USER_AGENT)
    delay = max(MIN_DELAY_SECONDS, min(float(delay), 30.0)) if delay is not None else MIN_DELAY_SECONDS
    return parser, sitemaps, delay


class PublicHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.jsonld: list[str] = []
        self.meta: dict[str, str] = {}
        self.title = ""
        self.words: list[str] = []
        self._script = False
        self._title = False
        self._blocked = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'a' and a.get('href'):
            self.links.append(a['href'])
        if tag == 'meta':
            key = (a.get('property') or a.get('name') or '').lower()
            if key and a.get('content'):
                self.meta[key] = a['content'][:300]
        if tag == 'script':
            self._script = a.get('type', '').lower().split(';')[0] == 'application/ld+json'
            if not self._script:
                self._blocked += 1
        if tag in ('style', 'noscript', 'svg'):
            self._blocked += 1
        if tag == 'title':
            self._title = True

    def handle_endtag(self, tag):
        if tag == 'script':
            if self._script:
                self._script = False
            elif self._blocked:
                self._blocked -= 1
        if tag in ('style', 'noscript', 'svg') and self._blocked:
            self._blocked -= 1
        if tag == 'title':
            self._title = False

    def handle_data(self, data):
        if self._script:
            if sum(map(len, self.jsonld)) < 100_000:
                self.jsonld.append(data)
        elif self._title:
            self.title += data
        elif not self._blocked and data.strip() and len(self.words) < 5000:
            self.words.append(' '.join(data.split()))


def _objects(parsed: PublicHTML):
    for text in parsed.jsonld:
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            continue
        stack = [data]
        while stack:
            item = stack.pop()
            if isinstance(item, list):
                stack.extend(reversed(item))
            elif isinstance(item, dict):
                yield item
                for key in ('@graph', 'itemListElement', 'mainEntity', 'item'):
                    if key in item:
                        stack.append(item[key])


def _address(obj):
    if isinstance(obj, list):
        obj = obj[0] if obj else None
    if not isinstance(obj, dict):
        return {}
    if 'address' in obj and isinstance(obj['address'], dict):
        obj = obj['address']
    return {
        'street': obj.get('streetAddress'),
        'neighborhood': obj.get('addressNeighborhood') or obj.get('neighborhood'),
        'city': obj.get('addressLocality'),
        'postal_code': obj.get('postalCode'),
    }


def _first(*values):
    return next((v for v in values if v is not None and v != ''), None)


def _transaction(text: str) -> str | None:
    if TRANSACTION_RENT.search(text):
        return 'rent'
    if TRANSACTION_SALE.search(text):
        return 'sale'
    return None


def _street_parts(value: str) -> tuple[str | None, str | None]:
    value = re.sub(r'\s+', ' ', value or '').strip()
    matched = STREET_RE.search(value)
    if matched:
        return matched.group(1).strip(' ,. -'), matched.group(2)
    # A street without number is retained as *partial*, never inferred.
    matched = STREET_ONLY_RE.search(value)
    if matched:
        return matched.group(1).strip(' ,. -'), None
    return value[:120] or None, None


def _structured_listing(obj, url: str):
    typ = obj.get('@type', [])
    types = {str(x).lower() for x in (typ if isinstance(typ, list) else [typ])}
    # ItemList/LocalBusiness/Organization often describe the site, not an individual unit.
    properties = {'apartment', 'singlefamilyresidence', 'house', 'residence', 'realestatelisting', 'accommodation', 'product'}
    if not types.intersection(properties):
        return None
    addr = obj.get('address')
    if isinstance(addr, str):
        addr = {'streetAddress':addr}
    location = _address(addr)
    geo = obj.get('geo') if isinstance(obj.get('geo'), dict) else {}
    offer = obj.get('offers')
    if isinstance(offer, list):
        offer = offer[0] if offer else None
    offer = offer if isinstance(offer, dict) else {}
    name = str(obj.get('name') or '')
    price = _first(offer.get('price'), obj.get('price'))
    if isinstance(price, str):
        price = re.sub(r'[^\d,.]', '', price)
    if price:
        try:
            price = float(str(price).replace('.', '').replace(',', '.')) if ',' in str(price) else float(price)
        except ValueError:
            price = None
    area = obj.get('floorSize') or obj.get('size')
    if isinstance(area, dict):
        area = area.get('value')
    try:
        area = float(area) if area else None
    except (TypeError, ValueError):
        area = None
    text = name+' '+str(obj.get('description') or '')+' '+url+' '+str(offer.get('name') or '')
    transaction = _transaction(text)
    # Property schema often omits the purpose; resolve against the page title
    # later rather than throwing away otherwise useful structured data.
    row = dict(location, transaction=transaction,
               property_type='Casa' if types.intersection({'house', 'singlefamilyresidence'}) else 'Apartamento',
               price=price, area=area, building_name=obj.get('name') if 'building' in name.lower() or 'edif' in name.lower() else None,
               latitude=geo.get('latitude'), longitude=geo.get('longitude'))
    # schema.org usually: streetAddress = 'Rua Nome, 123'. Never invent the number.
    if row.get('street'):
        row['street'], row['street_number'] = _street_parts(str(row['street']))
    return row


def parse_listing(html: str, url: str) -> tuple[dict | None, list[str]]:
    parsed = PublicHTML()
    parsed.feed(html)
    candidates = list(_objects(parsed))
    listing_data = next((r for obj in candidates if (r := _structured_listing(obj, url))), None)
    # Preserve text-node boundaries. Joining with spaces made address regexes
    # consume the following label, and could lose street numbers entirely.
    full_text = '\n'.join(parsed.words)[:35_000]
    title = (parsed.meta.get('og:title') or parsed.title or '')[:300]
    metadata = ' '.join(str(parsed.meta.get(k, '')) for k in ('description', 'og:description', 'twitter:description'))
    looks_like_listing = bool(LISTING_HINT.search(urlsplit(url).path) or DETAIL_HINT.search(urlsplit(url).path))
    # A listing card on a search-result page is NOT sufficient to identify one property.
    has_property_schema = listing_data is not None
    if not looks_like_listing and not has_property_schema:
        return None, parsed.links
    # Avoid treating search/index pages as individual properties.
    path = urlsplit(url).path.rstrip('/').lower()
    if INDEX_PATH.search(path):
        return None, parsed.links
    transaction = _transaction(title+' '+metadata+' '+url+' '+full_text[:3000])
    if not transaction and not (listing_data and listing_data.get('transaction')):
        return None, parsed.links
    row = listing_data or {'transaction': transaction}
    row['transaction'] = row.get('transaction') or transaction
    if not row.get('price'):
        m = MONEY_RE.search(full_text[:6000])
        if m:
            raw = m.group(1)
            row['price'] = float(raw.replace('.', '').replace(',', '.')) if ',' in raw else float(raw.replace('.', ''))
    if not row.get('street'):
        m = STREET_RE.search(full_text[:12000])
        if m:
            row['street'] = m.group(1).strip()
            row['street_number'] = m.group(2)
        elif (m := STREET_ONLY_RE.search(metadata)):
            row['street'] = m.group(1).strip(' ,. -')
    if not row.get('area'):
        m = AREA_RE.search(full_text[:9000])
        if m:
            row['area'] = float(m.group(1).replace(',', '.'))
    if not row.get('bedrooms'):
        m = BEDS_RE.search(full_text[:9000])
        if m:
            row['bedrooms'] = int(m.group(1))
    if not row.get('neighborhood'):
        m = ADDRESS_LABEL_RE.search(full_text[:8000])
        if m:
            row['neighborhood'] = m.group(1).strip(' -|,')[:80]
    if not row.get('city'):
        m = CITY_LABEL_RE.search(full_text[:8000])
        if m:
            row['city'] = m.group(1).strip(' -|,')[:80]
    if not row.get('property_type'):
        row['property_type'] = 'Casa' if 'casa' in (url+title).lower() else 'Apartamento'
    # Never store contact names, phone numbers, details not used for property analysis.
    if not (row.get('street') or row.get('neighborhood') or row.get('city')):
        return None, parsed.links
    # Guard against category/search pages being registered as individual ads.
    # Without schema, require a plausible detail URL AND a property signal.
    if not listing_data and not DETAIL_HINT.search(path):
        return None, parsed.links
    if not listing_data and not (row.get('price') or row.get('area') or row.get('bedrooms')):
        return None, parsed.links
    if not row.get('transaction'):
        return None, parsed.links
    row['url'] = url
    row['external_id'] = hashlib.sha256(url.encode('utf-8')).hexdigest()[:24]
    return row, parsed.links


def _sitemap_urls(xml: bytes, base: str, domain: str) -> tuple[list[str], list[str]]:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return [], []
    links, indexes = [], []
    is_index = root.tag.lower().endswith('sitemapindex')
    for el in root.iter():
        if not el.tag.lower().endswith('loc') or not el.text:
            continue
        url = _safe_link(el.text.strip(), base, domain)
        if not url:
            continue
        if is_index:
            if len(indexes) < 3:
                indexes.append(url)
        elif LISTING_HINT.search(urlsplit(url).path) or DETAIL_HINT.search(urlsplit(url).path):
            if len(links) < MAX_CANDIDATES:
                links.append(url)
    return links, indexes


def crawl_public_site(seed_url: str, *, max_pages: int = MAX_PAGES, fetch=None, sleep=None) -> tuple[list[dict], dict]:
    """Read permitted HTML pages from one domain, returning advertised properties only.

    fetch/sleep injection exists solely for isolated tests. No browser automation.
    """
    domain = _domain(seed_url)
    fetch = fetch or _fetch
    sleep = sleep or time.sleep
    robots, sitemaps, delay = _robots(seed_url, domain)
    if not sitemaps:
        sitemaps = [f'https://{domain}/sitemap.xml']
    queue = deque([seed_url])
    seen = set()
    queued = {seed_url}
    for sitemap in sitemaps[:3]:
        if not robots.can_fetch(USER_AGENT, sitemap):
            continue
        try:
            xml, _ = fetch(sitemap, domain, MAX_SITEMAP_BYTES)
            links, indexes = _sitemap_urls(xml, sitemap, domain)
            for link in links:
                if link not in queued:
                    queue.append(link)
                    queued.add(link)
            for child in indexes[:2]:
                if not robots.can_fetch(USER_AGENT, child):
                    continue
                try:
                    body, _ = fetch(child, domain, MAX_SITEMAP_BYTES)
                    found, _ = _sitemap_urls(body, child, domain)
                    for link in found:
                        if link not in queued:
                            queue.append(link)
                            queued.add(link)
                except (ScanError, FileNotFoundError):
                    pass
        except (ScanError, FileNotFoundError):
            pass
    rows, blocked, errors = [], 0, []
    reasons = {'not_listing':0, 'missing_data':0, 'unreadable':0}
    checked_urls = []
    count = 0
    max_pages = max(1, min(int(max_pages), MAX_PAGES))
    last_fetch = None
    while queue and count < max_pages and len(rows) < MAX_CANDIDATES:
        url = queue.popleft()
        if url in seen:
            continue
        seen.add(url)
        if not robots.can_fetch(USER_AGENT, url):
            blocked += 1
            continue
        if last_fetch is not None:
            sleep(delay)
        last_fetch = time.monotonic()
        try:
            body, ctype = fetch(url, domain, MAX_HTML_BYTES)
            if 'text/html' not in ctype:
                continue
            html = body.decode('utf-8-sig', 'replace')
            row, links = parse_listing(html, url)
            count += 1
            if len(checked_urls) < 4:
                checked_urls.append(url[:160])
            if row:
                rows.append(row)
            else:
                reasons['not_listing'] += 1
            for link in links[:250]:
                child = _safe_link(link, url, domain)
                if child and child not in seen and child not in queued and LISTING_HINT.search(urlsplit(child).path):
                    if len(queue) < MAX_CANDIDATES:
                        # Prioritize likely detail pages over catalog listings.
                        if DETAIL_HINT.search(urlsplit(child).path) and not INDEX_PATH.search(urlsplit(child).path):
                            queue.appendleft(child)
                        else:
                            queue.append(child)
                        queued.add(child)
        except FileNotFoundError:
            errors.append(f'Página inexistente: {url[:120]}')
        except ScanError as exc:
            errors.append(f'{url[:80]}: {exc}')
            reasons['unreadable'] += 1
    if count == 0:
        hint = (' Exemplos: ' + '; '.join(errors[:2])) if errors else ''
        raise ScanError('Nenhuma página HTML acessível. Confira a URL final HTTPS, robots.txt e bloqueios do site.' + hint)
    info = {'pages':count, 'discovered':len(seen), 'blocked':blocked, 'extracted':len(rows),
            'errors':errors[:4], 'reasons':reasons, 'sample_urls':checked_urls,
            'scope':'apenas domínio cadastrado; HTML público'}
    return rows, info
