import io
import json
from openpyxl import load_workbook


def load(client, records):
    res = client.post('/api/import/json', json=records)
    assert res.status_code == 200, res.text
    return res.json()


def test_health_and_static(client):
    assert client.get('/api/health').json()['status'] == 'ok'
    assert client.get('/').status_code == 200
    assert 'RADAR' in client.get('/').text
    assert client.get('/static/app.js').status_code == 200
    assert client.get('/api/example/csv').status_code == 200
    assert len(client.get('/api/example/demo').json()) >= 10


def test_normalizes_address_and_groups_building(client, records):
    assert load(client, records)['created'] == 2
    dashboard = client.get('/api/dashboard').json()
    assert dashboard['buildings'] == 1
    assert dashboard['total_listings'] == 2
    assert dashboard['full_address'] == 2
    b = client.get('/api/buildings').json()['items'][0]
    assert b['listings_count'] == 2
    assert b['units_estimated'] == 2
    assert b['confidence'] == 1


def test_partial_address_is_not_grouped_without_building_name(client):
    records = [
        {"source":"demo","external_id":"a","city":"Porto Alegre","neighborhood":"Centro","street":"Rua X"},
        {"source":"demo","external_id":"b","city":"Porto Alegre","neighborhood":"Centro","street":"Rua X"},
    ]
    load(client, records)
    d=client.get('/api/dashboard').json()
    assert d['unassigned']==2
    assert d['buildings']==0


def test_same_named_building_with_partial_address_requires_review(client):
    records = [
        {"city":"Porto Alegre","neighborhood":"Centro","street":"Rua X","building_name":"Torre Primavera","external_id":"1"},
        {"city":"Porto Alegre","neighborhood":"Centro","street":"Rua X","building_name":"Torre Primavera","external_id":"2"},
    ]
    load(client, records)
    d=client.get('/api/dashboard').json()
    assert d['buildings']==1 and d['for_review']==1
    b=client.get('/api/buildings').json()['items'][0]
    assert b['status']=='verify' and b['confidence'] < 1


def test_doesnt_merge_same_name_different_neighborhood(client):
    load(client,[
      {"city":"Porto Alegre","neighborhood":"Centro","building_name":"Torre Alfa","external_id":"1"},
      {"city":"Porto Alegre","neighborhood":"Rio Branco","building_name":"Torre Alfa","external_id":"2"},
    ])
    assert client.get('/api/dashboard').json()['buildings']==2


def test_reimport_updates_instead_of_duplicating(client, records):
    load(client, records)
    records[0]['price']=2999
    assert load(client, records)['updated']==2
    d=client.get('/api/dashboard').json()
    assert d['total_listings']==2
    price=client.get('/api/listings').json()['items']
    assert any(p['price']==2999 for p in price)


def test_duplicate_requires_same_unit_and_transaction(client, records):
    load(client, records)
    third={**records[0],"source":"Outro canal","external_id":"3","url":"https://example.org/listing/3"}
    outcome=load(client,[third]);assert outcome['duplicates']==1
    detail=client.get('/api/buildings').json()['items'][0]
    assert detail['listings_count']==3 and detail['units_estimated']==2
    fourth={**third,"source":"Outro canal","external_id":"4","url":"https://example.org/listing/4","unit_ref":None}
    assert load(client,[fourth])['duplicates']==0
    detail=client.get('/api/buildings').json()['items'][0]
    assert detail['units_estimated']==3


def test_status_notes_and_history(client, records):
    load(client,records)
    b=client.get('/api/buildings').json()['items'][0]
    patch=client.patch(f'/api/buildings/{b["id"]}',json={'status':'prospecting','notes':'Visitar na sexta'})
    assert patch.status_code==200
    assert patch.json()['status']=='prospecting'
    assert client.patch(f'/api/buildings/{b["id"]}',json={'status':'fake'}).status_code==422
    response=client.post(f'/api/buildings/{b["id"]}/activities',json={'message':'Contato com a portaria agendado'})
    assert response.status_code==201
    detail=client.get(f'/api/buildings/{b["id"]}').json()
    assert detail['notes']=='Visitar na sexta'
    assert len(detail['activities']) >= 3


def test_filters_and_pagination(client, records):
    load(client,records)
    res=client.get('/api/listings?transaction=rent&limit=1&page=2').json()
    assert res['page']==2 and res['total']==2 and len(res['items'])==1
    assert client.get('/api/buildings?status=verify').json()['total']==0
    assert client.get('/api/buildings?status=new').json()['total']==1


def test_import_csv_semicolon_and_xlsx(client):
    content='cidade;bairro;rua;numero;edificio;preco;finalidade\nPorto Alegre;Centro;Rua Teste;20;Edificio Central;2500;locacao\n'.encode('utf-8')
    res=client.post('/api/import/file',files={'file':('sample.csv',content,'text/csv')})
    assert res.status_code==200 and res.json()['created']==1
    exported=client.get('/api/export/buildings?format=xlsx')
    assert exported.status_code==200
    workbook=load_workbook(io.BytesIO(exported.content),read_only=True)
    assert workbook.active.max_row==2
    xlsx=client.get('/api/export/listings?format=xlsx')
    res=client.post('/api/import/file',files={'file':('copy.xlsx',xlsx.content,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})
    assert res.status_code==200
    workbook.close()


def test_csv_excel_injection_is_escaped(client):
    load(client,[{"source":"=HYPERLINK(\"evil\")","city":"Porto Alegre","street":"Rua X","street_number":"100"}])
    data=client.get('/api/export/listings?format=csv').content.decode('utf-8-sig')
    assert "'=HYPERLINK" in data
    data=client.get('/api/export/listings?format=xlsx').content
    workbook=load_workbook(io.BytesIO(data),read_only=True)
    assert any(str(v).startswith("'=HYPERLINK") for row in workbook.active.iter_rows(values_only=True) for v in row if v is not None)
    workbook.close()


def test_invalid_file_and_row_errors_are_reported(client):
    assert client.post('/api/import/file',files={'file':('bad.txt',b'abc')}).status_code==415
    assert client.post('/api/import/file',files={'file':('bad.csv',b'xxx')}).status_code==422
    response=load(client,[{'cidade':'Porto Alegre','preco':'abc'}, {'cidade':'Porto Alegre','preco':'1200'}])
    assert response['created']==1 and response['failed']==1
    assert response['errors'][0]['row']==2


def test_rejects_overlimit(client):
    response=client.post('/api/import/json',json=[{'city':'X'}]*2501)
    assert response.status_code==413


def test_delete_listing_releases_duplicate_references(client, records):
    load(client,records)
    load(client,[{**records[0], 'source':'Outra origem','external_id':'222'}])
    listing=client.get('/api/listings').json()['items']
    root=next(x for x in listing if x['external_id']=='1')
    dup=next(x for x in listing if x['external_id']=='222')
    assert dup['duplicate_of']==root['id']
    assert client.delete(f'/api/listings/{root["id"]}').status_code==200
    dup_updated=next(x for x in client.get('/api/listings').json()['items'] if x['external_id']=='222')
    assert dup_updated['duplicate_of'] is None


def test_no_location_is_no_building(client):
    load(client,[{'source':'Teste','external_id':'1','url':'https://example.com/listing/1'}])
    assert client.get('/api/dashboard').json()['unassigned']==1
