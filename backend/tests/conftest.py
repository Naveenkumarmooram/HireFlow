# ruff: noqa: E402
# Set test-only configuration before importing the application.
import os

os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["JWT_SECRET"] = "test-only-signing-key-never-use-in-production"
os.environ["AUTO_MIGRATE_ON_STARTUP"] = "false"
os.environ["CORS_ORIGINS"] = "http://localhost:5173"


from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Organization, User
from app.security import hash_password


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with TestingSession() as db:
        organization = Organization(name="Test Org")
        db.add(organization)
        db.flush()
        db.add(
            User(
                organization_id=organization.id,
                email="recruiter@example.com",
                name="Test Recruiter",
                role="admin",
                password_hash=hash_password("correct-horse-battery-staple"),
            )
        )
        db.commit()

    def override_get_db():
        with TestingSession() as db:
            yield db

    @asynccontextmanager
    async def test_lifespan(_app):
        yield

    app.dependency_overrides[get_db] = override_get_db
    app.state.test_session_factory = TestingSession
    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = test_lifespan
    with TestClient(app) as test_client:
        yield test_client
    app.router.lifespan_context = original_lifespan
    app.dependency_overrides.clear()
    del app.state.test_session_factory
    Base.metadata.drop_all(engine)
    engine.dispose()
