"""Regression tests for pages that previously produced false zero-results."""
import threading
import time
from urllib.request import Request

from fastapi.testclient import TestClient

from app import crawler
from app.crawler import _safe_link, parse_listing, crawl_public_site, StrictRedirect, ScanError
from app.main import create_app

ROOT = 'https://pesquisa-imobiliaria.example'


def test_canonical_listing_url_keeps_pagination_but_drops_tracking():
    link = _safe_link('/imoveis?utm_source=ads&pagina=3&page=2&id=45&session=abc', ROOT, 'pesquisa-imobiliaria.example')
    assert link == ROOT + '/imoveis?pagina=3&page=2&id=45'
    assert _safe_link('https://outra.example/imovel/3', ROOT, 'pesquisa-imobiliaria.example') is None


def test_schema_transaction_can_come_from_page_title():
    html = '''<html><head><title>Apartamento à venda em Porto Alegre</title>
    <script type="application/ld+json">{
       "@type":"Apartment", "name":"Apartamento com varanda",
       "address":{"streetAddress":"Rua João Alfredo, 250",
                  "addressNeighborhood":"Cidade Baixa","addressLocality":"Porto Alegre"},
       "offers":{"price":380000},"floorSize":{"value":68}}
    </script></head></html>'''
    row, _ = parse_listing(html, ROOT + '/imovel/123456')
    assert row['transaction'] == 'sale'
    assert row['street_number'] == '250'
    assert row['price'] == 380000


def test_detail_page_without_jsonld_can_be_read_from_visible_html():
    html = '''<html><head><title>Casa para alugar — Imobiliária</title>
    <meta name="description" content="Casa localizada na Rua General Lima e Silva, 340, Cidade Baixa"></head>
    <body><h1>Casa para locação</h1><span>R$ 2.500</span>
    <p>Bairro: Cidade Baixa</p><p>Cidade: Porto Alegre</p>
    <p>Rua General Lima e Silva, 340</p><p>80 m² e 2 quartos</p></body></html>'''
    row, _ = parse_listing(html, ROOT + '/detalhes/98765')
    assert row is not None
    assert row['transaction'] == 'rent'
    assert row['street_number'] == '340'
    assert row['area'] == 80


def test_search_page_is_not_accidentally_treated_as_single_property():
    page = '''<html><head><title>Imóveis à venda</title></head><body>
    Rua Flores, 100 — R$ 350.000 — 50 m² <a href="/imovel/12345">Detalhes</a></body></html>'''
    row, links = parse_listing(page, ROOT + '/imoveis?pagina=2')
    assert row is None
    assert links == ['/imovel/12345']


def test_crawler_prioritizes_detail_pages_from_homepage(monkeypatch):
    class Robots:
        def can_fetch(self, agent, url):
            return True
    monkeypatch.setattr(crawler, '_robots', lambda url, domain: (Robots(), [], 0))
    html = '<html><head><title>Imobiliária</title></head><body><a href="/imoveis">Imóveis</a><a href="/detalhes/98765">Apartamento</a></body></html>'
    detail = '''<html><head><title>Apartamento para alugar</title></head><body>
    <p>Rua dos Andradas, 900</p><p>Bairro: Centro Histórico</p><p>R$ 3000</p><p>63 m²</p></body></html>'''
    def fake_fetch(url, domain, limit):
        if url.endswith('/sitemap.xml'):
            raise FileNotFoundError(url)
        return ((detail if url.endswith('/detalhes/98765') else html).encode(), 'text/html')
    rows, stats = crawl_public_site(ROOT, max_pages=2, fetch=fake_fetch, sleep=lambda _: None)
    assert stats['pages'] == 2
    assert stats['extracted'] == 1
    assert rows[0]['street_number'] == '900'


def test_zero_results_explained_in_source_run(tmp_path, monkeypatch):
    monkeypatch.setattr(crawler, 'crawl_public_site', lambda url: ([], {
        'pages': 5, 'extracted': 0, 'blocked': 0,
        'reasons': {'not_listing': 5, 'unreadable': 0}, 'errors': []}))
    with TestClient(create_app('sqlite://', imports_dir=tmp_path)) as client:
        sid = client.post('/api/sources', json={
            'name':'Teste de diagnóstico', 'kind':'web', 'location':ROOT}).json()['id']
        response = client.post(f'/api/sources/{sid}/run')
        assert response.status_code == 200
        assert response.json()['status'] == 'partial'
        assert '5 páginas' in response.json()['message']
        assert 'formato ainda não suportado' in response.json()['message']
        assert client.get('/api/sources').json()['items'][0]['last_error'] is not None


def test_failed_scan_creates_single_finished_run(tmp_path, monkeypatch):
    def fail(url):
        raise ScanError('Acesso não permitido por robots.txt')
    monkeypatch.setattr(crawler, 'crawl_public_site', fail)
    with TestClient(create_app('sqlite://', imports_dir=tmp_path)) as client:
        sid = client.post('/api/sources', json={
            'name':'Teste de falha', 'kind':'web', 'location':ROOT}).json()['id']
        response = client.post(f'/api/sources/{sid}/run')
        assert response.json()['status'] == 'error'
        runs = client.get(f'/api/sources/{sid}/runs').json()['items']
        assert len(runs) == 1
        assert runs[0]['finished_at'] is not None


def test_background_scan_is_visible_while_it_is_running(tmp_path, monkeypatch):
    monkeypatch.setenv('RADAR_AUTO_SYNC', '0')
    entered, resume = threading.Event(), threading.Event()
    def blocked_scan(url):
        entered.set()
        assert resume.wait(5), 'test crawl unexpectedly timed out'
        return ([], {'pages': 2, 'extracted': 0, 'blocked': 0,
                     'reasons': {'not_listing': 2}, 'errors': []})
    monkeypatch.setattr(crawler, 'crawl_public_site', blocked_scan)
    # Disk SQLite uses independent connections across threads, like the
    # actual Windows installation. sqlite:// memory uses one shared connection.
    with TestClient(create_app(f"sqlite:///{tmp_path / 'scan.db'}", imports_dir=tmp_path)) as client:
        sid = client.post('/api/sources', json={
            'name': 'Teste de progresso', 'kind': 'web', 'location': ROOT}).json()['id']
        assert client.post(f'/api/sources/{sid}/start').status_code == 202
        assert entered.wait(2)
        try:
            for _ in range(30):
                items = client.get(f'/api/sources/{sid}/runs').json()['items']
                if items:
                    break
                time.sleep(0.01)
            assert len(items) == 1
            assert items[0]['status'] == 'running'
            assert items[0]['finished_at'] is None
        finally:
            resume.set()
        for _ in range(100):
            items = client.get(f'/api/sources/{sid}/runs').json()['items']
            if items[0]['status'] != 'running':
                break
            time.sleep(0.01)
        assert items[0]['status'] == 'partial'
        assert len(items) == 1


def test_same_host_redirect_allowed_and_cross_host_rejected():
    handler = StrictRedirect()
    old = Request(ROOT+'/imoveis')
    assert handler.redirect_request(old, None, 301, 'Moved', {}, ROOT+'/imoveis/') is not None
    try:
        handler.redirect_request(old, None, 301, 'Moved', {}, 'https://outro.example/imoveis/')
    except ScanError as exc:
        assert 'inseguro' in str(exc)
    else:
        raise AssertionError('Redirect to another host must be denied')
