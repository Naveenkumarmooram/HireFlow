"""Security regressions exercise authorization and failure behavior through HTTP."""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from sqlalchemy import select
from test_api import auth_header  # shared integration fixture

from app.config import Settings, settings
from app.main import app
from app.models import Candidate, Organization, User
from app.security import hash_password


def add_user(email, role="interviewer", other_tenant=False):
    with app.state.test_session_factory() as db:
        if other_tenant:
            org = Organization(name="Other tenant")
            db.add(org)
            db.flush()
        else:
            org = db.scalar(select(Organization).where(Organization.name == "Test Org"))
        user = User(
            organization_id=org.id,
            email=email,
            name="Test user",
            role=role,
            password_hash=hash_password("strong-password-for-tests"),
        )
        db.add(user)
        db.commit()
        return user.id


def user_headers(client, email):
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": "strong-password-for-tests"},
    )
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def test_interviewer_cannot_read_compensation_or_tenant_summary(client):
    add_user("interviewer@example.com")
    headers = user_headers(client, "interviewer@example.com")
    assert client.get("/api/offers", headers=headers).status_code == 403
    assert client.get("/api/dashboard/summary", headers=headers).status_code == 403


def test_cross_tenant_candidate_access_and_assignment_are_denied(client):
    headers = auth_header(client)
    foreign_id = add_user("foreign@example.com", "admin", True)
    foreign_headers = user_headers(client, "foreign@example.com")
    candidate = client.post(
        "/api/candidates",
        headers=foreign_headers,
        json={
            "name": "Private Person",
            "email": "private@example.com",
            "role_title": "Engineer",
        },
    ).json()
    assert client.get("/api/candidates", headers=headers).json() == []
    assert (
        client.patch(
            "/api/candidates/" + candidate["id"],
            headers=headers,
            json={"stage": "Hired"},
        ).status_code
        == 404
    )
    assert client.delete("/api/candidates/" + candidate["id"], headers=headers).status_code == 404
    assert (
        client.get("/api/candidates/" + candidate["id"] + "/resumes", headers=headers).status_code
        == 404
    )
    assert (
        client.patch(
            "/api/users/" + foreign_id, headers=headers, json={"active": False}
        ).status_code
        == 404
    )


def test_logout_revokes_existing_tokens(client):
    headers = auth_header(client)
    assert client.post("/api/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_password_change_invalidates_old_password_and_sessions(client):
    headers = auth_header(client)
    assert (
        client.post(
            "/api/auth/password",
            headers=headers,
            json={
                "current_password": "correct-horse-battery-staple",
                "new_password": "new-safe-password-value",
            },
        ).status_code
        == 204
    )
    assert client.get("/api/auth/me", headers=headers).status_code == 401
    assert (
        client.post(
            "/api/auth/login",
            json={
                "email": "recruiter@example.com",
                "password": "correct-horse-battery-staple",
            },
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/auth/login",
            json={
                "email": "recruiter@example.com",
                "password": "new-safe-password-value",
            },
        ).status_code
        == 200
    )


def test_disable_user_revokes_access_and_last_admin_is_preserved(client):
    headers = auth_header(client)
    user_id = add_user("member@example.com")
    member_headers = user_headers(client, "member@example.com")
    assert (
        client.patch("/api/users/" + user_id, headers=headers, json={"active": False}).status_code
        == 200
    )
    assert client.get("/api/auth/me", headers=member_headers).status_code == 401
    admin_id = client.get("/api/auth/me", headers=headers).json()["id"]
    assert (
        client.patch(
            "/api/users/" + admin_id, headers=headers, json={"role": "recruiter"}
        ).status_code
        == 409
    )


def test_tokens_require_expiry_and_correct_audience(client):
    token = auth_header(client)["Authorization"].split()[1]
    claims = jwt.decode(
        token, settings.jwt_secret, algorithms=["HS256"], audience=settings.jwt_audience
    )
    for key, value in [("aud", "other-product"), ("iss", "other-issuer"), ("exp", 0)]:
        forged = jwt.encode({**claims, key: value}, settings.jwt_secret, algorithm="HS256")
        assert (
            client.get("/api/auth/me", headers={"Authorization": "Bearer " + forged}).status_code
            == 401
        )
    del claims["exp"]
    forged = jwt.encode(claims, settings.jwt_secret, algorithm="HS256")
    assert (
        client.get("/api/auth/me", headers={"Authorization": "Bearer " + forged}).status_code == 401
    )


def test_login_throttle_is_persistent_and_does_not_store_email(client, monkeypatch):
    from app.models import LoginAttempt

    monkeypatch.setattr(settings, "login_attempt_limit", 3)
    for _ in range(3):
        assert (
            client.post(
                "/api/auth/login",
                json={"email": "missing@example.com", "password": "bad"},
            ).status_code
            == 401
        )
    response = client.post(
        "/api/auth/login", json={"email": "missing@example.com", "password": "bad"}
    )
    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0
    with app.state.test_session_factory() as db:
        attempt = db.scalar(select(LoginAttempt))
        assert len(attempt.key) == 64
        assert "missing" not in attempt.key


def test_cors_put_security_headers_and_body_limit(client, monkeypatch):
    response = client.options(
        "/api/settings",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code == 200
    assert "PUT" in response.headers["access-control-allow-methods"]
    assert (
        client.options(
            "/api/settings",
            headers={
                "Origin": "https://evil.example",
                "Access-Control-Request-Method": "PUT",
            },
        ).status_code
        == 400
    )
    response = client.get("/api/health")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-request-id"]
    monkeypatch.setattr(settings, "max_request_bytes", 1024)
    assert client.post("/api/auth/login", content=b"x" * 1025).status_code == 413


def test_validation_does_not_echo_passwords(client):
    secret = "z" * 257
    response = client.post("/api/auth/login", json={"email": "not-an-email", "password": secret})
    assert response.status_code == 422
    assert secret not in response.text
    assert '"input"' not in response.text


def test_candidate_null_and_blank_fields_rejected(client):
    headers = auth_header(client)
    assert (
        client.post(
            "/api/candidates",
            headers=headers,
            json={"name": " ", "email": "a@example.com", "role_title": "Engineer"},
        ).status_code
        == 422
    )
    candidate = client.post(
        "/api/candidates",
        headers=headers,
        json={"name": "Person", "email": "a@example.com", "role_title": "Engineer"},
    ).json()
    for field in ("stage", "skills", "experience"):
        assert (
            client.patch(
                "/api/candidates/" + candidate["id"],
                headers=headers,
                json={field: None},
            ).status_code
            == 422
        )
    assert (
        client.patch(
            "/api/candidates/" + candidate["id"], headers=headers, json={"email": None}
        ).status_code
        == 200
    )
    assert client.get("/api/candidates?limit=201", headers=headers).status_code == 422


def test_interview_requires_timezone_aware_date(client):
    headers = auth_header(client)
    response = client.post(
        "/api/interviews",
        headers=headers,
        json={
            "candidate_id": "unused",
            "title": "Interview",
            "scheduled_for": "2026-10-05T10:00:00",
            "timezone": "Invalid/Zone",
        },
    )
    assert response.status_code == 422


def test_expired_offer_is_not_public_and_decision_is_one_time(client):
    from app.models import Offer

    headers = auth_header(client)
    candidate = client.post(
        "/api/candidates",
        headers=headers,
        json={"name": "Person", "email": "offer@example.com", "role_title": "Engineer"},
    ).json()
    offer = client.post(
        "/api/offers",
        headers=headers,
        json={
            "candidate_id": candidate["id"],
            "title": "Engineer",
            "compensation": "100",
            "employment_type": "Full time",
        },
    ).json()
    token = offer["acceptance_url"].split("/")[-1]
    assert (
        client.post("/api/offers/" + offer["id"] + "/approve", headers=headers).status_code == 200
    )
    assert (
        client.post("/api/public/offers/" + token + "/decision?decision=accept").status_code == 200
    )
    assert (
        client.post("/api/public/offers/" + token + "/decision?decision=decline").status_code == 404
    )
    with app.state.test_session_factory() as db:
        row = db.get(Offer, offer["id"])
        row.status = "approved"
        row.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        db.commit()
    assert client.get("/api/public/offers/" + token).status_code == 410
    assert (
        client.post("/api/public/offers/" + token + "/decision?decision=accept").status_code == 410
    )


def test_unverified_applicant_cannot_read_or_withdraw_existing_profile(client):
    headers = auth_header(client)
    candidate = client.post(
        "/api/candidates",
        headers=headers,
        json={
            "name": "Confidential Name",
            "email": "known@example.com",
            "role_title": "Engineer",
        },
    ).json()
    job = client.post(
        "/api/jobs", headers=headers, json={"title": "Open job", "status": "published"}
    ).json()
    receipt = client.post(
        "/api/public/jobs/" + job["id"] + "/applications",
        json={"name": "Submitted Name", "email": "known@example.com", "consent": True},
    ).json()
    token = receipt["portal_url"].split("/")[-1]
    portal = client.get("/api/public/candidates/" + token)
    assert "Confidential Name" not in portal.text
    assert portal.json()["interviews"] == []
    assert portal.json()["offer_status"] is None
    assert client.post("/api/public/candidates/" + token + "/withdraw").status_code == 200
    with app.state.test_session_factory() as db:
        assert db.get(Candidate, candidate["id"]).stage == "New"


@pytest.mark.parametrize(
    "overrides",
    [
        {"jwt_secret": "short"},
        {"database_url": "sqlite:///local.db"},
        {"database_url": "postgresql+psycopg://user:password@db.example/postgres"},
        {"cors_origins": "*"},
        {"cors_origins": "http://localhost:5173"},
        {"auto_migrate_on_startup": True},
    ],
)
def test_production_rejects_unsafe_settings(overrides):
    values = {
        "environment": "production",
        "jwt_secret": "a" * 48,
        "database_url": "postgresql+psycopg://user:password@db.example/postgres?sslmode=require",
        "cors_origins": "https://app.example.com",
        "auto_migrate_on_startup": False,
    }
    with pytest.raises(ValueError):
        Settings(_env_file=None, **{**values, **overrides})


def test_dashboard_summary_aggregates_without_loading_private_rows(client):
    response = client.get("/api/dashboard/summary", headers=auth_header(client))
    assert response.status_code == 200
    assert response.json()["active_candidates"] == 0
