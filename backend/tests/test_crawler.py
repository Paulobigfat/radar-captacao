"""Offline and deterministic tests. No third-party site is contacted."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.crawler import ScanError, _robots, crawl_public_site, parse_listing
from app.main import create_app
from app.regions import zone_for

ROOT = 'https://teste-imobiliaria.example'
HOME = ROOT + '/imoveis'
DETAIL = ROOT + '/imovel/apartamento-aluguel-123'
PUBLIC_LISTING = '''<!doctype html><html><head><title>Apartamento para alugar - Porto Alegre</title>
<script type="application/ld+json">{
 "@context":"https://schema.org", "@type":"Apartment", "name":"Apartamento para alugar",
 "address":{"@type":"PostalAddress","streetAddress":"Avenida Ipiranga, 550",
 "addressLocality":"Porto Alegre","addressNeighborhood":"Jardim Botânico","addressRegion":"RS"},
 "offers":{"price":"2200", "priceCurrency":"BRL"}, "floorSize":{"value":55}
}</script></head><body><div>Aluguel R$ 2.200 · 55 m²</div>
<a href="/contato">Contato</a></body></html>'''


def test_extract_public_address_without_guessing():
    row, links = parse_listing(PUBLIC_LISTING, DETAIL)
    assert row['street'] == 'Avenida Ipiranga'
    assert row['street_number'] == '550'
    assert row['city'] == 'Porto Alegre'
    assert row['neighborhood'] == 'Jardim Botânico'
    assert row['price'] == 2200
    assert row['transaction'] == 'rent'
    assert zone_for(row['city'], row['neighborhood']) == 'Zona Leste'
    assert row['external_id']
    assert links == ['/contato']


def test_no_inference_of_hidden_address():
    html = '''<html><head><title>Apartamento para alugar</title>
      <script type="application/ld+json">{"@type":"Apartment","name":"Apartamento para alugar",
      "address":{"addressNeighborhood":"Tristeza","addressLocality":"Porto Alegre"}}</script>
      </head><body>Bairro: Tristeza</body></html>'''
    row, _ = parse_listing(html, ROOT+'/imovel/aluguel-sem-numero')
    assert row['street'] is None and row.get('street_number') is None
    assert row['city'] == 'Porto Alegre'
    assert zone_for(row['city'], row['neighborhood']) == 'Zona Sul'


def test_robots_exclusion(monkeypatch):
    from app import crawler
    def fake_fetch(url, domain, max_bytes):
        assert url.endswith('/robots.txt')
        return (b'User-agent: *\nDisallow: /imoveis\n', 'text/plain')
    monkeypatch.setattr(crawler, '_fetch', fake_fetch)
    with pytest.raises(ScanError, match='robots.txt'):
        crawler.crawl_public_site(HOME)


def test_sitemap_and_public_links_without_api(monkeypatch):
    from app import crawler
    class Robots:
        def can_fetch(self, agent, url):
            return '/contato' not in url
    monkeypatch.setattr(crawler, '_robots', lambda seed, domain: (Robots(), [ROOT+'/sitemap.xml'], 0))
    def fake_fetch(url, domain, max_bytes):
        assert domain == 'teste-imobiliaria.example'
        if url.endswith('sitemap.xml'):
            return (f'<urlset><url><loc>{DETAIL}</loc></url></urlset>'.encode(), 'application/xml')
        if url == HOME:
            return (f'<html><a href="{DETAIL}">Anúncio</a><a href="https://elsewhere.example/imovel">Outro site</a></html>'.encode(), 'text/html')
        if url == DETAIL:
            return (PUBLIC_LISTING.encode(), 'text/html')
        raise AssertionError('URL inesperada: '+url)
    rows, summary = crawl_public_site(HOME, fetch=fake_fetch, sleep=lambda _: None)
    assert len(rows)==1
    assert rows[0]['street_number']=='550'
    assert summary['pages']==2
    assert summary['extracted']==1


def test_web_source_persists_advertised_unit_without_explicit_feed_rights(tmp_path,monkeypatch):
    from app import crawler
    monkeypatch.setattr(crawler, 'crawl_public_site',
                        lambda location: ([parse_listing(PUBLIC_LISTING, DETAIL)[0]],
                                          {'pages':2,'extracted':1,'discovered':2,'blocked':0,'errors':[]}))
    with TestClient(create_app('sqlite://', imports_dir=tmp_path)) as client:
        response=client.post('/api/sources', json={
            'name':'Imobiliária teste', 'kind':'web', 'location':HOME, 'interval_minutes':60,
            'rights_confirmed':False})
        assert response.status_code==201, response.text
        sid=response.json()['id']
        first=client.post(f'/api/sources/{sid}/run')
        assert first.json()['status']=='ok', first.text
        assert first.json()['created']==1
        second=client.post(f'/api/sources/{sid}/run')
        assert second.json()['updated']==1
        data=client.get('/api/reports/availability?zone=Zona%20Leste').json()
        assert data['total']==1
        row=data['items'][0]
        assert row['street_number']=='550' and row['zone']=='Zona Leste'
        assert 'endereço' in data['disclaimer'].lower()
        exported=client.get('/api/reports/availability/export?format=csv&zone=Zona%20Leste')
        assert exported.status_code==200 and b'Zona Leste' in exported.content


def test_web_source_rejects_local_and_http(tmp_path):
    with TestClient(create_app('sqlite://', imports_dir=tmp_path)) as client:
        for url in ['http://example.com/imoveis','https://127.0.0.1/imoveis',
                    'https://localhost/imoveis','https://example.com:8443/imoveis']:
            res=client.post('/api/sources',json={'name':'Teste', 'kind':'web', 'location':url})
            assert res.status_code==422, (url,res.text)
