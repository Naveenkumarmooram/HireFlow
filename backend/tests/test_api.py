from fastapi.testclient import TestClient

from app.main import app
from app.models import Organization, User
from app.security import hash_password


def auth_header(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={
            "email": "recruiter@example.com",
            "password": "correct-horse-battery-staple",
        },
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_login_rejects_invalid_password(client: TestClient):
    response = client.post(
        "/api/auth/login", json={"email": "recruiter@example.com", "password": "wrong"}
    )
    assert response.status_code == 401


def test_health_endpoint_checks_database(client: TestClient):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_candidate_create_update_and_screening(client: TestClient):
    headers = auth_header(client)
    created = client.post(
        "/api/candidates",
        headers=headers,
        json={
            "name": "Jordan Lee",
            "email": "jordan@example.com",
            "role_title": "Python Developer",
            "skills": ["Python", "FastAPI"],
            "experience": "3 years",
        },
    )
    assert created.status_code == 201
    candidate = created.json()
    assert candidate["skills"] == ["Python", "FastAPI"]

    screening = client.post(
        f"/api/candidates/{candidate['id']}/screenings",
        headers=headers,
        json={
            "call_status": "Connected",
            "current_ctc": "4.2 LPA",
            "expected_ctc": "6.0 LPA",
            "notice_period": "15 days",
            "relocation": "Yes",
            "contract_preference": "Not discussed",
            "notes": "Available for technical round",
            "decision": "Shortlist",
        },
    )
    assert screening.status_code == 201
    assert screening.json()["decision"] == "Shortlist"

    rows = client.get("/api/candidates", headers=headers)
    assert rows.status_code == 200
    assert rows.json()[0]["stage"] == "Tech round 1"
    assert rows.json()[0]["availability"] == "15 days"


def test_candidate_routes_require_authentication(client: TestClient):
    assert client.get("/api/candidates").status_code == 401
    assert client.post("/api/candidates", json={}).status_code == 401


def test_interviewer_cannot_access_recruiter_candidate_routes(client: TestClient):
    with app.state.test_session_factory() as db:
        organization = db.query(Organization).filter_by(name="Test Org").one()
        db.add(
            User(
                organization_id=organization.id,
                email="interviewer@example.com",
                name="Interviewer",
                role="interviewer",
                password_hash=hash_password("interviewer-password"),
            )
        )
        db.commit()
    response = client.post(
        "/api/auth/login",
        json={"email": "interviewer@example.com", "password": "interviewer-password"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    assert (
        client.post(
            "/api/candidates", headers={"Authorization": f"Bearer {token}"}, json={}
        ).status_code
        == 403
    )


def test_public_application_matching_and_duplicate_detection(client: TestClient):
    headers = auth_header(client)
    job_response = client.post(
        "/api/jobs",
        headers=headers,
        json={
            "title": "Python Engineer",
            "location": "Bengaluru",
            "employment_type": "Full time",
            "status": "published",
            "description": "Build reliable services.",
            "requirements": [
                {"skill": "Python", "category": "must_have", "weight": 2},
                {"skill": "PostgreSQL", "category": "nice_to_have", "weight": 1},
            ],
        },
    )
    assert job_response.status_code == 201
    job_id = job_response.json()["id"]
    assert len(client.get("/api/public/jobs").json()) == 1

    application_data = {
        "name": "Casey Candidate",
        "email": "casey@example.com",
        "experience": "2 years",
        "skills": ["Python"],
        "consent": True,
    }
    application = client.post(f"/api/public/jobs/{job_id}/applications", json=application_data)
    assert application.status_code == 201
    portal_url = application.json()["portal_url"]
    portal_token = portal_url.split("/")[-1]
    portal = client.get(f"/api/public/candidates/{portal_token}")
    assert portal.status_code == 200
    assert portal.json()["application_status"] == "Applied"
    candidate = client.get("/api/candidates", headers=headers).json()[0]
    assert candidate["stage"] == "Applied"
    score = client.post(f"/api/candidates/{candidate['id']}/match?job_id={job_id}", headers=headers)
    assert score.status_code == 200
    assert score.json()["score"] == 67
    assert "has not been verified" in score.json()["criteria"][0]["evidence"]
    duplicate = client.post(f"/api/public/jobs/{job_id}/applications", json=application_data)
    assert duplicate.status_code == 409
    assert (
        client.post(
            f"/api/public/jobs/{job_id}/applications",
            json={**application_data, "consent": False},
        ).status_code
        == 400
    )
    assert (
        client.post(f"/api/public/candidates/{portal_token}/withdraw").json()["status"]
        == "withdrawn"
    )
    assert client.get("/api/candidates", headers=headers).json()[0]["stage"] == "Candidate Withdrew"


def test_interview_offer_tasks_team_settings_and_audit(client: TestClient):
    headers = auth_header(client)
    candidate_response = client.post(
        "/api/candidates",
        headers=headers,
        json={
            "name": "Jordan Lee",
            "email": "jordan@example.com",
            "role_title": "Backend Engineer",
        },
    )
    candidate_id = candidate_response.json()["id"]

    interview_response = client.post(
        "/api/interviews",
        headers=headers,
        json={
            "candidate_id": candidate_id,
            "title": "Technical Round 1",
            "scheduled_for": "2026-10-05T10:00:00+05:30",
            "duration_minutes": 60,
            "timezone": "Asia/Kolkata",
            "meeting_method": "In person",
        },
    )
    assert interview_response.status_code == 201
    interview_id = interview_response.json()["id"]
    feedback = client.post(
        f"/api/interviews/{interview_id}/feedback",
        headers=headers,
        json={
            "technical_rating": 4,
            "problem_solving_rating": 5,
            "evidence": "Explained API design tradeoffs and tested failure cases.",
            "recommendation": "Yes",
        },
    )
    assert feedback.status_code == 201

    offer_response = client.post(
        "/api/offers",
        headers=headers,
        json={
            "candidate_id": candidate_id,
            "title": "Backend Engineer",
            "compensation": "₹8 LPA",
            "employment_type": "Full time",
            "joining_date": "2026-11-02",
        },
    )
    assert offer_response.status_code == 201
    offer = offer_response.json()
    assert client.post(f"/api/offers/{offer['id']}/approve", headers=headers).status_code == 200
    acceptance_token = offer["acceptance_url"].split("/")[-1]
    assert client.get(f"/api/public/offers/{acceptance_token}").status_code == 200
    assert (
        client.post(f"/api/public/offers/{acceptance_token}/decision?decision=accept").json()[
            "status"
        ]
        == "accepted"
    )

    task = client.post(
        "/api/tasks",
        headers=headers,
        json={"candidate_id": candidate_id, "title": "Confirm start date"},
    )
    assert task.status_code == 201
    assert (
        client.patch(
            f"/api/tasks/{task.json()['id']}", headers=headers, json={"status": "done"}
        ).json()["status"]
        == "done"
    )
    teammate = client.post(
        "/api/users",
        headers=headers,
        json={
            "name": "Interviewer One",
            "email": "interviewer-one@example.com",
            "password": "safe-development-password",
            "role": "interviewer",
        },
    )
    assert teammate.status_code == 201
    settings_response = client.put(
        "/api/settings",
        headers=headers,
        json={"timezone": "Asia/Kolkata", "retention_days": 730},
    )
    assert settings_response.status_code == 200
    assert settings_response.json()["timezone"] == "Asia/Kolkata"
    assert client.get("/api/audit-events", headers=headers).json()


def test_candidate_history_and_communication_drafts_are_stored_not_sent(
    client: TestClient,
):
    headers = auth_header(client)
    candidate_response = client.post(
        "/api/candidates",
        headers=headers,
        json={
            "name": "Sam Example",
            "email": "sam@example.com",
            "role_title": "Data Engineer",
            "expected_ctc": "7 LPA",
        },
    )
    candidate_id = candidate_response.json()["id"]
    templates = client.get("/api/communications/templates", headers=headers)
    assert templates.status_code == 200
    template = next(
        item for item in templates.json() if item["event_key"] == "interview_invitation"
    )
    edited = client.put(
        f"/api/communications/templates/{template['id']}",
        headers=headers,
        json={
            "name": template["name"],
            "body": template["body"],
            "event_key": template["event_key"],
            "subject": "Meet us: {{role}}",
        },
    )
    assert edited.status_code == 200
    template = edited.json()
    draft = client.post(
        "/api/communications/drafts",
        headers=headers,
        json={"template_id": template["id"], "candidate_id": candidate_id},
    )
    assert draft.status_code == 201
    assert draft.json()["status"] == "draft"
    assert "Sam Example" in draft.json()["body"]
    assert "Data Engineer" in draft.json()["subject"]
    assert client.get("/api/communications/outbox", headers=headers).json()[0]["status"] == "draft"
    activity = client.get(f"/api/candidates/{candidate_id}/activity", headers=headers)
    assert activity.status_code == 200
    assert any(item["action"] == "created" for item in activity.json())


def test_resume_upload_requires_supported_type_and_configured_scanner(
    client: TestClient, monkeypatch
):
    from app.config import settings

    headers = auth_header(client)
    candidate = client.post(
        "/api/candidates",
        headers=headers,
        json={
            "name": "Resume Test",
            "email": "resume@example.com",
            "role_title": "Engineer",
        },
    ).json()
    monkeypatch.setattr(settings, "clamd_host", "")
    unsupported = client.post(
        f"/api/candidates/{candidate['id']}/resumes",
        headers=headers,
        files={"file": ("resume.exe", b"MZ", "application/octet-stream")},
    )
    assert unsupported.status_code == 415
    disabled = client.post(
        f"/api/candidates/{candidate['id']}/resumes",
        headers=headers,
        files={"file": ("resume.pdf", b"%PDF-1.7", "application/pdf")},
    )
    assert disabled.status_code == 503
    assert "malware scanning" in disabled.json()["detail"]


def test_resume_is_scanned_encrypted_and_downloaded_only_through_authorized_route(
    client: TestClient, monkeypatch
):
    from io import BytesIO

    from cryptography.fernet import Fernet
    from pypdf import PdfWriter

    from app.config import settings
    from app.models import ResumeDocument

    headers = auth_header(client)
    candidate = client.post(
        "/api/candidates",
        headers=headers,
        json={
            "name": "Secure Resume",
            "email": "secure-resume@example.com",
            "role_title": "Engineer",
        },
    ).json()
    monkeypatch.setattr(settings, "clamd_host", "scanner.test")
    monkeypatch.setattr(settings, "resume_encryption_key", Fernet.generate_key().decode())

    class CleanScanner:
        def instream(self, _file):
            return {"stream": ("OK", None)}

    monkeypatch.setattr("app.services.clamd.ClamdNetworkSocket", lambda **_kwargs: CleanScanner())
    buffer = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.write(buffer)
    pdf_bytes = buffer.getvalue()

    upload = client.post(
        f"/api/candidates/{candidate['id']}/resumes",
        headers=headers,
        files={"file": ("resume.pdf", pdf_bytes, "application/pdf")},
    )
    assert upload.status_code == 201
    resume = upload.json()
    assert resume["original_name"] == "resume.pdf"
    assert (
        client.post(
            f"/api/candidates/{candidate['id']}/resumes",
            headers=headers,
            files={"file": ("copy.pdf", pdf_bytes, "application/pdf")},
        ).status_code
        == 409
    )

    with app.state.test_session_factory() as db:
        stored = db.get(ResumeDocument, resume["id"])
        assert stored.encrypted_content != pdf_bytes

    download = client.get(
        f"/api/candidates/{candidate['id']}/resumes/{resume['id']}/download",
        headers=headers,
    )
    assert download.status_code == 200
    assert download.content == pdf_bytes
    assert (
        client.get(f"/api/candidates/{candidate['id']}/resumes/{resume['id']}/download").status_code
        == 401
    )


def test_resume_first_intake_creates_candidate_without_manual_contact_entry(
    client: TestClient, monkeypatch
):
    from io import BytesIO
    from zipfile import ZIP_DEFLATED, ZipFile

    from cryptography.fernet import Fernet

    from app.config import settings

    headers = auth_header(client)
    monkeypatch.setattr(settings, "clamd_host", "scanner.test")
    monkeypatch.setattr(settings, "resume_encryption_key", Fernet.generate_key().decode())

    class CleanScanner:
        def instream(self, _file):
            return {"stream": ("OK", None)}

    monkeypatch.setattr("app.services.clamd.ClamdNetworkSocket", lambda **_kwargs: CleanScanner())
    document = b'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Python Developer resume with 3 years experience and Django</w:t></w:r></w:p></w:body></w:document>'
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", document)
    response = client.post(
        "/api/resume-intake",
        headers=headers,
        data={"role_title": "Python Developer"},
        files={
            "file": (
                "Jamie_Rivera.docx",
                buffer.getvalue(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert response.status_code == 201
    result = response.json()
    assert result["candidate"]["name"] == "Jamie Rivera"
    assert result["candidate"]["email"] is None
    assert result["candidate"]["stage"] == "Resume Parsed"
    assert "email" in result["fields_needing_review"]
    assert "Python" in result["candidate"]["skills"]
