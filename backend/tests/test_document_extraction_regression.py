"""Regression tests for document extraction: roll synonyms, answer parsing variants, LLM fallback gating, and bulk upload persistence."""

import os
import time
import uuid
from typing import Dict, List

import fitz
import pytest
import requests


def _resolve_base_url() -> str:
    env_url = os.environ.get("REACT_APP_BACKEND_URL")
    if env_url:
        return env_url.rstrip("/")

    with open("/app/frontend/.env", "r", encoding="utf-8") as env_file:
        for line in env_file:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().strip('"').rstrip("/")

    raise RuntimeError("REACT_APP_BACKEND_URL is not set")


BASE_URL = _resolve_base_url()
API_BASE = f"{BASE_URL}/api"


def _build_pdf_bytes(lines: List[str]) -> bytes:
    document = fitz.open()
    page = document.new_page()
    y = 72
    for line in lines:
        page.insert_text((72, y), line, fontsize=11)
        y += 16
    pdf_bytes = document.tobytes()
    document.close()
    return pdf_bytes


def _poll_job_until_completed(api_client: requests.Session, auth_headers: Dict[str, str], job_id: str, timeout_seconds: int = 120) -> Dict:
    start = time.time()
    latest = None
    while time.time() - start < timeout_seconds:
        response = api_client.get(f"{API_BASE}/jobs/{job_id}", headers=auth_headers, timeout=30)
        assert response.status_code == 200, response.text
        latest = response.json()
        if latest["status"] == "completed":
            return latest
        time.sleep(2)
    pytest.fail(f"Job {job_id} did not complete in time. Last payload: {latest}")


@pytest.fixture(scope="module")
def api_client() -> requests.Session:
    client = requests.Session()
    client.headers.update({"Accept": "application/json"})
    return client


@pytest.fixture(scope="module")
def instructor_context(api_client: requests.Session) -> Dict[str, str]:
    suffix = uuid.uuid4().hex[:8]
    email = f"test_extract_{suffix}@example.com"
    password = "testpass123"

    register_payload = {"name": "TEST Extractor", "email": email, "password": password}
    register_response = api_client.post(f"{API_BASE}/auth/register", json=register_payload, timeout=30)
    assert register_response.status_code == 200, register_response.text
    register_data = register_response.json()
    assert register_data["email"] == email

    login_response = api_client.post(f"{API_BASE}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert login_response.status_code == 200, login_response.text
    token = login_response.json().get("access_token")
    assert isinstance(token, str) and len(token) > 20

    headers = {"Authorization": f"Bearer {token}"}
    session_payload = {
        "title": f"TEST Extraction Session {suffix}",
        "question_paper_text": "Question 1: Explain process. Question 2: Define concept.",
        "answer_key_text": "Q1 expected details. Q2 expected details.",
        "rubric_text": "Q1: 5 marks. Q2: 5 marks.",
        "ai_provider": "gemini",
    }
    session_response = api_client.post(f"{API_BASE}/sessions", json=session_payload, headers=headers, timeout=30)
    assert session_response.status_code == 200, session_response.text
    session_id = session_response.json()["id"]

    return {"auth_headers": headers, "session_id": session_id}


# Module: document_processing.py roll synonym + answer variant extraction path via /bulk-upload
def test_bulk_upload_pdf_detects_registration_number_and_answer_variants(api_client: requests.Session, instructor_context: Dict[str, str]):
    file_name = f"student_variant_{uuid.uuid4().hex[:6]}.pdf"
    pdf_payload = _build_pdf_bytes(
        [
            "Student Name: Alice Variant",
            "Registration Number: REG-2026-01",
            "Question 1: First answer line.",
            "Que 2) Second answer line.",
        ]
    )

    upload_response = api_client.post(
        f"{API_BASE}/sessions/{instructor_context['session_id']}/bulk-upload",
        files=[("files", (file_name, pdf_payload, "application/pdf"))],
        headers=instructor_context["auth_headers"],
        timeout=60,
    )
    assert upload_response.status_code == 200, upload_response.text
    job_id = upload_response.json()["id"]
    _poll_job_until_completed(api_client, instructor_context["auth_headers"], job_id)

    list_response = api_client.get(
        f"{API_BASE}/sessions/{instructor_context['session_id']}/submissions",
        headers=instructor_context["auth_headers"],
        timeout=30,
    )
    assert list_response.status_code == 200, list_response.text
    matched = [item for item in list_response.json() if item["filename"] == file_name]
    assert len(matched) == 1

    submission = matched[0]
    assert submission["student_name"] == "Alice Variant"
    assert submission["roll_number"] == "REG-2026-01"
    assert submission["answers"]["Q1"].startswith("First answer line")
    assert submission["answers"]["Q2"].startswith("Second answer line")
    assert "LLM-assisted extraction applied" not in submission.get("extraction_flags", [])


# Module: document_processing.py numbering forms like "1)" and "Ans 2" parsing via /bulk-upload
def test_bulk_upload_pdf_parses_numbering_styles_1_and_ans(api_client: requests.Session, instructor_context: Dict[str, str]):
    file_name = f"student_numbering_{uuid.uuid4().hex[:6]}.pdf"
    pdf_payload = _build_pdf_bytes(
        [
            "Name: Bob Numbering",
            "Candidate ID: CID7788",
            "1) One style answer paragraph.",
            "Ans 2: Two style answer paragraph.",
        ]
    )

    upload_response = api_client.post(
        f"{API_BASE}/sessions/{instructor_context['session_id']}/bulk-upload",
        files=[("files", (file_name, pdf_payload, "application/pdf"))],
        headers=instructor_context["auth_headers"],
        timeout=60,
    )
    assert upload_response.status_code == 200, upload_response.text
    job_id = upload_response.json()["id"]
    _poll_job_until_completed(api_client, instructor_context["auth_headers"], job_id)

    list_response = api_client.get(
        f"{API_BASE}/sessions/{instructor_context['session_id']}/submissions",
        headers=instructor_context["auth_headers"],
        timeout=30,
    )
    assert list_response.status_code == 200, list_response.text
    matched = [item for item in list_response.json() if item["filename"] == file_name]
    assert len(matched) == 1

    submission = matched[0]
    assert submission["student_name"] == "Bob Numbering"
    assert submission["roll_number"] == "CID7788"
    assert "Q1" in submission["answers"]
    assert "Q2" in submission["answers"]


# Module: document_processing.py fallback gate - LLM assist should only happen for incomplete rule extraction
def test_llm_assist_flag_only_for_incomplete_extraction(api_client: requests.Session, instructor_context: Dict[str, str]):
    complete_name = f"complete_{uuid.uuid4().hex[:6]}.txt"
    incomplete_name = f"incomplete_{uuid.uuid4().hex[:6]}.txt"

    complete_text = (
        "Student Name: Complete Student\n"
        "Roll No: C-100\n"
        "Question 1: Complete answer one.\n"
        "Question 2: Complete answer two.\n"
    ).encode("utf-8")
    incomplete_text = (
        "This is an unstructured response without explicit metadata. "
        "It includes a long body paragraph meant to trigger fallback extraction. " * 8
    ).encode("utf-8")

    upload_response = api_client.post(
        f"{API_BASE}/sessions/{instructor_context['session_id']}/bulk-upload",
        files=[
            ("files", (complete_name, complete_text, "text/plain")),
            ("files", (incomplete_name, incomplete_text, "text/plain")),
        ],
        headers=instructor_context["auth_headers"],
        timeout=60,
    )
    assert upload_response.status_code == 200, upload_response.text
    job_id = upload_response.json()["id"]
    _poll_job_until_completed(api_client, instructor_context["auth_headers"], job_id, timeout_seconds=180)

    list_response = api_client.get(
        f"{API_BASE}/sessions/{instructor_context['session_id']}/submissions",
        headers=instructor_context["auth_headers"],
        timeout=30,
    )
    assert list_response.status_code == 200, list_response.text
    submissions = list_response.json()

    complete = [item for item in submissions if item["filename"] == complete_name][0]
    incomplete = [item for item in submissions if item["filename"] == incomplete_name][0]

    assert "LLM-assisted extraction applied" not in complete.get("extraction_flags", [])
    assert "LLM-assisted extraction applied" in incomplete.get("extraction_flags", [])
    assert complete["roll_number"] == "C-100"
