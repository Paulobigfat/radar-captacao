"""Authorized sources: repeatability, failure isolation and basic network restrictions."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient
from app.main import create_app
from app.sources import parse_feed, validate_feed_url
import pytest


def build_client(tmp_path):
    app = create_app('sqlite://', imports_dir=tmp_path)
    return TestClient(app)


def test_local_file_sync_is_idempotent(tmp_path):
    records = [
        {"id_externo":"f-1", "cidade":"Porto Alegre", "bairro":"Centro", "rua":"Rua Um", "numero":"12", "edificio":"Torre Um", "preco":2100},
        {"id_externo":"f-2", "cidade":"Porto Alegre", "bairro":"Centro", "rua":"Rua Um", "numero":"12", "edificio":"Torre Um", "preco":2400},
    ]
    (tmp_path / 'feed.json').write_text(json.dumps(records), encoding='utf-8')
    with build_client(tmp_path) as client:
        res = client.post('/api/sources',json={
          'name':'Fonte Parceira', 'kind':'file','location':'feed.json',
          'interval_minutes':15,'rights_confirmed':True,
        })
        assert res.status_code == 201, res.text
        sid=res.json()['id']
        first=client.post(f'/api/sources/{sid}/run')
        assert first.status_code==200,first.text
        assert first.json()['created']==2
        assert client.get('/api/dashboard').json()['buildings']==1
        second=client.post(f'/api/sources/{sid}/run')
        assert second.json()['created']==0 and second.json()['updated']==2
        assert client.get('/api/dashboard').json()['total_listings']==2
        records[0]['preco']=2600
        (tmp_path / 'feed.json').write_text(json.dumps(records),encoding='utf-8')
        third=client.post(f'/api/sources/{sid}/run')
        assert third.json()['status']=='ok'
        prices=[l['price'] for l in client.get('/api/listings').json()['items']]
        assert 2600 in prices
        history=client.get(f'/api/sources/{sid}/runs').json()['items']
        assert len(history)==3 and history[0]['updated']==2
        assert client.patch(f'/api/sources/{sid}',json={'enabled':False}).json()['enabled']==False
        assert client.delete(f'/api/sources/{sid}').json()['listings_preserved']==True
        assert client.get('/api/dashboard').json()['total_listings']==2


def test_invalid_url_or_rights_rejected(tmp_path):
    with build_client(tmp_path) as client:
        base={'name':'Feed ruim','kind':'https','rights_confirmed':True,'location':'https://127.0.0.1/feed.json'}
        assert client.post('/api/sources',json=base).status_code==422
        for url in ['http://example.com/feed.json','https://localhost/feed.json','https://10.0.0.2/feed.json','https://[::1]/feed.json','https://example.com:8443/feed.json','https://u:p@example.com/feed.json']:
            assert client.post('/api/sources',json={**base,'location':url}).status_code==422, url
        assert client.post('/api/sources',json={**base,'location':'https://example.com/feed.json','rights_confirmed':False}).status_code==422
        assert client.post('/api/sources',json={**base,'kind':'file','location':'../secrets.json'}).status_code==422


def test_failed_feed_preserves_existing_data(tmp_path):
    file=tmp_path / 'feed.csv'
    file.write_text('id_externo;cidade;rua;numero\n1;Porto Alegre;Rua Um;11\n',encoding='utf-8')
    with build_client(tmp_path) as client:
        sid=client.post('/api/sources',json={'name':'Arquivo CSV','kind':'file','location':'feed.csv','rights_confirmed':True}).json()['id']
        assert client.post(f'/api/sources/{sid}/run').json()['created']==1
        file.write_text('id_externo;cidade;rua;numero\n;Porto Alegre;Rua Dois;12\n',encoding='utf-8')
        failed=client.post(f'/api/sources/{sid}/run').json()
        assert failed['status']=='error'
        assert client.get('/api/dashboard').json()['total_listings']==1
        assert client.get('/api/sources').json()['items'][0]['last_error']
        assert client.get(f'/api/sources/{sid}/runs').json()['items'][0]['status']=='error'


def test_empty_feed_and_private_url(tmp_path, monkeypatch):
    import socket
    assert parse_feed(b'{"items":[{"id_externo":"2"}]}', 'https://x.org/data')==[{'id_externo':'2'}]
    with pytest.raises(ValueError): parse_feed(b'[]', 'feed.json')
    from app.sources import public_address_only
    def loopback(*args,**kwargs):return [(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',443))]
    monkeypatch.setattr(socket,'getaddrinfo',loopback)
    with pytest.raises(ValueError):public_address_only('evil.test')


def test_file_symlink_escape_rejected(tmp_path):
    outside=tmp_path.parent / 'outside-feed.json'
    outside.write_text('[{"id_externo":"1"}]',encoding='utf-8')
    link=tmp_path / 'escape.json'
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip('Symlinks not supported')
    with build_client(tmp_path) as client:
        sid=client.post('/api/sources',json={'name':'Arquivo externo','kind':'file','location':'escape.json','rights_confirmed':True}).json()['id']
        result=client.post(f'/api/sources/{sid}/run').json()
        assert result['status']=='error'
    outside.unlink(missing_ok=True)
