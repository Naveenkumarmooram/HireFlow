"""Exercise the real migration chain, independent of ORM create_all tests."""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

ROOT = Path(__file__).resolve().parents[1]


def test_migrate_empty_database_and_repeat(tmp_path):
    # TEST_DATABASE_URL is only supplied for the disposable PostgreSQL CI service.
    url = os.environ.get(
        "TEST_DATABASE_URL",
        "sqlite+pysqlite:///" + (tmp_path / "migrations.db").as_posix(),
    )
    env = {
        **os.environ,
        "DATABASE_URL": url,
        "ENVIRONMENT": "test",
        "AUTO_MIGRATE_ON_STARTUP": "false",
    }
    for _ in range(2):
        result = subprocess.run(
            [sys.executable, "build.py"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, "Migration failed: " + result.stderr
    engine = create_engine(url)
    assert "login_attempts" in inspect(engine).get_table_names()
    assert any(column["name"] == "token_version" for column in inspect(engine).get_columns("users"))
    with engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            == "0006_auth_hardening"
        )
        if engine.dialect.name == "postgresql":
            assert connection.scalar(
                text("SELECT relrowsecurity FROM pg_class WHERE relname = 'users'")
            )
    engine.dispose()


def test_bootstrap_is_explicit_and_existing_credentials_are_preserved(tmp_path):
    env = {
        **os.environ,
        "DATABASE_URL": "sqlite+pysqlite:///" + (tmp_path / "bootstrap.db").as_posix(),
        "ENVIRONMENT": "test",
        "BOOTSTRAP_ORG_NAME": "Smoke test",
        "BOOTSTRAP_ADMIN_EMAIL": "admin@example.com",
        "BOOTSTRAP_ADMIN_PASSWORD": "isolated-test-password-only",
    }
    for args in [["build.py"], ["-m", "app.bootstrap"], ["-m", "app.bootstrap"]]:
        result = subprocess.run(
            [sys.executable, *args], cwd=ROOT, env=env, capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr
    code = """
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as client:
    assert client.get('/api/health').status_code == 200
    response = client.post('/api/auth/login', json={'email':'admin@example.com','password':'isolated-test-password-only'})
    assert response.status_code == 200
    headers = {'Authorization':'Bearer '+response.json()['access_token']}
    assert client.post('/api/candidates', headers=headers, json={'name':'Migration smoke','email':'smoke@example.com','role_title':'Engineer'}).status_code == 201
"""
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    env["BOOTSTRAP_ADMIN_EMAIL"] = "second@example.com"
    result = subprocess.run(
        [sys.executable, "-m", "app.bootstrap"], cwd=ROOT, env=env, capture_output=True, text=True
    )
    assert result.returncode != 0
    assert "already provisioned" in result.stderr
