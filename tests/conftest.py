import pytest

from lazyticket import db, seed
from lazyticket.config import Settings


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    db.init_db(path)
    return path


@pytest.fixture
def seeded(db_path):
    seed.seed(db_path)
    return db_path


@pytest.fixture
def settings(db_path):
    return Settings(ollama_host="http://127.0.0.1:9", ollama_model="gemma3:4b",
                    ollama_timeout=2, db_path=db_path)
