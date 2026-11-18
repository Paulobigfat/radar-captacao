"""Load fictitious demonstration data explicitly: python -m app.seed"""
import json
from pathlib import Path
from .main import app
from .logic import map_input, ingest


def main():
    data = json.loads((Path(__file__).resolve().parents[2]/"examples"/"demo.json").read_text(encoding="utf-8"))
    with app.state.SessionLocal() as db:
        for record in data:
            ingest(db, map_input(record))
        db.commit()
    print(f"Dados fictícios importados: {len(data)} anúncios")


if __name__ == "__main__":
    main()
