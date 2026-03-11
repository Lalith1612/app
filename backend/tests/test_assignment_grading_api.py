"""API regression tests for auth, session lifecycle, upload/grading jobs, review, analytics and export."""

import io
import os
import time
import uuid
import zipfile

import pytest
import requests


def _resolve_base_url() -> str:
    env_url = os.environ.get("REACT_APP_BACKEND_URL")
    if env_url:
        return env_url.rstrip("/")

    frontend_env = "/app/frontend/.env"
    if os.path.exists(frontend_env):
        with open(frontend_env, "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().strip('"').rstrip("/")

    raise RuntimeError("REACT_APP_BACKEND_URL is not set")


BASE_URL = _resolve_base_url()
API_BASE = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def api_client():
    session = requests.Session()
    session.headers.update({"Accept": "application/json"})
    return session


@pytest.fixture(scope="module")
def workflow_context(api_client):
    suffix = uuid.uuid4().hex[:8]
    email = f"test_instructor_{suffix}@example.com"
    password = "testpass123"
    name = "TEST Instructor"

    register_payload = {"name": name, "email": email, "password": password}
    register_response = api_client.post(f"{API_BASE}/auth/register", json=register_payload, timeout=30)
    assert register_response.status_code == 200, register_response.text
    register_data = register_response.json()
    assert register_data["email"] == email
    assert register_data["name"] == name
    assert register_data["role"] == "instructor"

    login_response = api_client.post(
        f"{API_BASE}/auth/login", json={"email": email, "password": password}, timeout=30
    )
    assert login_response.status_code == 200, login_response.text
    token = login_response.json().get("access_token")
    assert isinstance(token, str) and len(token) > 20

    auth_headers = {"Authorization": f"Bearer {token}"}

    session_payload = {
        "title": f"TEST Session {suffix}",
        "question_paper_text": "Q1: Explain photosynthesis. Q2: Define osmosis.",
        "answer_key_text": "Q1: Photosynthesis converts light energy into chemical energy. Q2: Osmosis is movement of water through semipermeable membrane.",
        "rubric_text": "Q1: 5 marks for correct process and equation. Q2: 5 marks for accurate definition.",
        "ai_provider": "gemini",
    }
    create_session_response = api_client.post(
        f"{API_BASE}/sessions", json=session_payload, headers=auth_headers, timeout=30
    )
    assert create_session_response.status_code == 200, create_session_response.text
    session_data = create_session_response.json()
    assert session_data["title"] == session_payload["title"]
    assert session_data["ai_provider"] == "gemini"

    return {
        "email": email,
        "password": password,
        "token": token,
        "auth_headers": auth_headers,
        "session_id": session_data["id"],
    }


def _poll_job_until_done(api_client, auth_headers, job_id, timeout_seconds=180):
    start = time.time()
    latest_data = None
    while time.time() - start < timeout_seconds:
        response = api_client.get(f"{API_BASE}/jobs/{job_id}", headers=auth_headers, timeout=30)
        assert response.status_code == 200, response.text
        latest_data = response.json()
        if latest_data["status"] == "completed":
            return latest_data
        time.sleep(2)
    pytest.fail(f"Job {job_id} did not complete in {timeout_seconds}s. Last state: {latest_data}")


def test_auth_me_requires_token(api_client):
    response = api_client.get(f"{API_BASE}/auth/me", timeout=30)
    assert response.status_code == 401
    data = response.json()
    assert data["detail"] == "Not authenticated"


def test_auth_me_success(workflow_context, api_client):
    response = api_client.get(f"{API_BASE}/auth/me", headers=workflow_context["auth_headers"], timeout=30)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["email"] == workflow_context["email"]
    assert data["role"] == "instructor"


def test_session_created_and_listed(workflow_context, api_client):
    response = api_client.get(f"{API_BASE}/sessions", headers=workflow_context["auth_headers"], timeout=30)
    assert response.status_code == 200, response.text
    sessions = response.json()
    assert isinstance(sessions, list)
    assert any(item["id"] == workflow_context["session_id"] for item in sessions)


def test_bulk_upload_txt_and_zip_and_job_progress(workflow_context, api_client):
    txt_bytes = (
        b"Student Name: Alice Example\nRoll Number: R001\nQ1: Photosynthesis converts light to chemical energy.\nQ2: Osmosis moves water across membrane."
    )

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "student2.txt",
            "Student Name: Bob Example\nRoll Number: R002\nQ1: Chlorophyll captures light.\nQ2: Osmosis is passive movement.",
        )
    zip_buffer.seek(0)

    files = [
        ("files", ("student1.txt", txt_bytes, "text/plain")),
        ("files", ("batch.zip", zip_buffer.read(), "application/zip")),
    ]

    response = api_client.post(
        f"{API_BASE}/sessions/{workflow_context['session_id']}/bulk-upload",
        files=files,
        headers=workflow_context["auth_headers"],
        timeout=60,
    )
    assert response.status_code == 200, response.text
    job = response.json()
    assert job["job_type"] == "upload"
    assert job["status"] in ["queued", "running", "completed"]
    assert job["total_items"] == 2

    completed = _poll_job_until_done(api_client, workflow_context["auth_headers"], job["id"])
    assert completed["status"] == "completed"
    assert completed["processed_items"] == 2


def test_submissions_listing_has_extracted_fields(workflow_context, api_client):
    response = api_client.get(
        f"{API_BASE}/sessions/{workflow_context['session_id']}/submissions",
        headers=workflow_context["auth_headers"],
        timeout=30,
    )
    assert response.status_code == 200, response.text
    submissions = response.json()
    assert len(submissions) >= 2
    sample = submissions[0]
    assert isinstance(sample["student_name"], str)
    assert isinstance(sample["roll_number"], str)
    assert isinstance(sample["answers"], dict)
    assert "status" in sample


def test_grading_job_gemini_completes(workflow_context, api_client):
    response = api_client.post(
        f"{API_BASE}/sessions/{workflow_context['session_id']}/grade",
        json={"ai_provider": "gemini"},
        headers=workflow_context["auth_headers"],
        timeout=30,
    )
    assert response.status_code == 200, response.text
    job = response.json()
    assert job["job_type"] == "grading"

    completed = _poll_job_until_done(api_client, workflow_context["auth_headers"], job["id"], timeout_seconds=240)
    assert completed["status"] == "completed"


def test_grading_job_local_mode_completes(workflow_context, api_client):
    response = api_client.post(
        f"{API_BASE}/sessions/{workflow_context['session_id']}/grade",
        json={"ai_provider": "local"},
        headers=workflow_context["auth_headers"],
        timeout=30,
    )
    assert response.status_code == 200, response.text
    job = response.json()
    assert job["job_type"] == "grading"

    completed = _poll_job_until_done(api_client, workflow_context["auth_headers"], job["id"], timeout_seconds=240)
    assert completed["status"] == "completed"


def test_manual_review_update_and_approve(workflow_context, api_client):
    submissions_response = api_client.get(
        f"{API_BASE}/sessions/{workflow_context['session_id']}/submissions",
        headers=workflow_context["auth_headers"],
        timeout=30,
    )
    assert submissions_response.status_code == 200, submissions_response.text
    submissions = submissions_response.json()
    target = submissions[0]

    grading_lines = target.get("grading") or [{"question_id": "Q1", "score": 3, "max_marks": 5, "reason": "Manual"}]
    payload = {
        "grading": grading_lines,
        "approved": True,
        "review_note": "Reviewed and approved by instructor",
    }
    review_response = api_client.put(
        f"{API_BASE}/submissions/{target['id']}/manual-review",
        json=payload,
        headers=workflow_context["auth_headers"],
        timeout=30,
    )
    assert review_response.status_code == 200, review_response.text
    updated = review_response.json()
    assert updated["status"] == "approved"
    assert updated["review_note"] == payload["review_note"]


def test_analytics_endpoint_response_shape(workflow_context, api_client):
    response = api_client.get(
        f"{API_BASE}/sessions/{workflow_context['session_id']}/analytics",
        headers=workflow_context["auth_headers"],
        timeout=30,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "average" in data and isinstance(data["average"], (int, float))
    assert "distribution" in data and isinstance(data["distribution"], list)
    assert "question_difficulty" in data and isinstance(data["question_difficulty"], list)
    assert data["total_submissions"] >= 1


def test_excel_export_downloadable(workflow_context, api_client):
    response = api_client.get(
        f"{API_BASE}/sessions/{workflow_context['session_id']}/export",
        headers=workflow_context["auth_headers"],
        timeout=60,
    )
    assert response.status_code == 200, response.text
    content_type = response.headers.get("content-type", "")
    assert "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in content_type
    assert len(response.content) > 100
