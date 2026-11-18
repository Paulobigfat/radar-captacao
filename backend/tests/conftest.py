import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import create_app


@pytest.fixture
def client():
    # Isolated in-memory SQLite database per test.
    app = create_app("sqlite://")
    with TestClient(app) as c:
        yield c


@pytest.fixture
def records():
    return [
        {"source": "Fonte autorizada", "external_id": "1", "transaction": "rent", "price": 2800,
         "area": 66, "bedrooms": 2, "city": "Porto Alegre", "neighborhood": "Petrópolis",
         "street": "Av. Ipiranga", "street_number": "123", "building_name": "Edifício Alpha", "unit_ref": "201"},
        {"source": "Fonte autorizada", "external_id": "2", "transaction": "rent", "price": 3000,
         "area": 70, "bedrooms": 2, "city": "Porto Alegre", "neighborhood": "Petrópolis",
         "street": "Avenida Ipiranga", "street_number": "123", "building_name": "Edifício Alpha", "unit_ref": "301"},
    ]
