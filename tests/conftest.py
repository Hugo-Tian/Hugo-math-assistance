import pytest
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from backend.db import Base, make_engine, get_db
from backend.main import app
from backend.seed import seed
from backend.models import User
from backend.security import passwords, login_throttle

@pytest.fixture(autouse=True)
def reset_login_throttle():
    login_throttle.failures.clear()

@pytest.fixture
def env(tmp_path):
    engine = make_engine(f'sqlite:///{tmp_path}/test.db')
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        seed(db, demos=False)
        db.add(User(username='admin', password_hash=passwords.hash('Password123!'), role='admin'))
        db.commit()
    def override():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = override
    with TestClient(app) as client:
        yield client, factory
    app.dependency_overrides.clear()
    engine.dispose()

@pytest.fixture
def learner(env):
    client, _ = env
    r = client.post('/api/auth/register', json={'username':'learner','password':'Password123!'}).json()
    return {'Authorization':f'Bearer {r["token"]}'}
