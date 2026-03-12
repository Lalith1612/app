import asyncio
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Dict, List

import pandas as pd
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask
from motor.motor_asyncio import AsyncIOMotorClient

try:
    from auth_utils import (
        create_access_token,
        decode_token,
        get_password_hash,
        get_token_from_auth,
        verify_password,
    )
    from document_processing import expand_submission_file, is_allowed_file, extract_student_information
    from grading_engine import grade_answers, parse_max_marks_map
    from plagiarism_engine import calculate_plagiarism_flags
    from schemas import (
        GradeJobRequest,
        InstructorResponse,
        JobResponse,
        LoginRequest,
        ManualReviewRequest,
        ModelChoiceRequest,
        RegisterRequest,
        SessionCreateRequest,
        SessionResponse,
        SubmissionResponse,
        TokenResponse,
    )
except ImportError:
    from .auth_utils import (
        create_access_token,
        decode_token,
        get_password_hash,
        get_token_from_auth,
        verify_password,
    )
    from .document_processing import expand_submission_file, is_allowed_file, extract_student_information
    from .grading_engine import grade_answers, parse_max_marks_map
    from .plagiarism_engine import calculate_plagiarism_flags
    from .schemas import (
        GradeJobRequest,
        InstructorResponse,
        JobResponse,
        LoginRequest,
        ManualReviewRequest,
        ModelChoiceRequest,
        RegisterRequest,
        SessionCreateRequest,
        SessionResponse,
        SubmissionResponse,
        TokenResponse,
    )


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")

# Use certifi CA bundle for Atlas TLS (fixes SSL handshake errors)
try:
    import certifi
    client = AsyncIOMotorClient(mongo_url, tlsCAFile=certifi.where())
except ImportError:
    client = AsyncIOMotorClient(mongo_url)

db = client[os.environ.get("DB_NAME", "zengrade")]

app = FastAPI(title="AI Assignment Grading System", version="1.0.0")
api_router = APIRouter(prefix="/api")

MAX_FILE_SIZE_MB = 15
JOBS: Dict[str, Dict] = {}

# Serve built React frontend if it exists
FRONTEND_BUILD = Path(__file__).parent.parent / "frontend" / "build"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def get_current_instructor(token: str = Depends(get_token_from_auth)) -> Dict:
    email = decode_token(token)
    user = await db.instructors.find_one({"email": email}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def _validate_owner(resource: Dict, instructor_email: str) -> None:
    if resource.get("created_by") != instructor_email:
        raise HTTPException(status_code=403, detail="You are not allowed to access this resource")


@app.on_event("startup")
async def startup_indexes() -> None:
    try:
        await db.instructors.create_index("email", unique=True)
        await db.sessions.create_index("id", unique=True)
        await db.submissions.create_index("id", unique=True)
        await db.jobs.create_index("id", unique=True)
    except Exception as e:
        print(f"WARNING: Could not create indexes: {e}")


@api_router.get("/")
async def root() -> Dict[str, str]:
    return {"message": "AI Assignment Grading API is running"}


@api_router.post("/auth/register", response_model=InstructorResponse)
async def register(payload: RegisterRequest) -> InstructorResponse:
    existing = await db.instructors.find_one({"email": payload.email}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    now = utcnow()
    instructor = {
        "id": str(uuid.uuid4()),
        "name": payload.name,
        "email": payload.email,
        "password_hash": get_password_hash(payload.password),
        "role": "instructor",
        "created_at": now,
    }
    await db.instructors.insert_one(instructor)
    response_doc = {k: v for k, v in instructor.items() if k != "password_hash"}
    return InstructorResponse(**response_doc)


@api_router.post("/auth/login", response_model=TokenResponse)
async def login(payload: LoginRequest) -> TokenResponse:
    user = await db.instructors.find_one({"email": payload.email}, {"_id": 0})
    if not user or not verify_password(payload.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return TokenResponse(access_token=create_access_token(user["email"]))


@api_router.get("/auth/me", response_model=InstructorResponse)
async def me(current: Dict = Depends(get_current_instructor)) -> InstructorResponse:
    doc = {k: v for k, v in current.items() if k != "password_hash"}
    return InstructorResponse(**doc)


@api_router.post("/sessions", response_model=SessionResponse)
async def create_session(payload: SessionCreateRequest, current: Dict = Depends(get_current_instructor)) -> SessionResponse:
    now = utcnow()
    session_doc = {
        "id": str(uuid.uuid4()),
        "title": payload.title,
        "question_paper_text": payload.question_paper_text,
        "answer_key_text": payload.answer_key_text,
        "rubric_text": payload.rubric_text,
        "ai_provider": payload.ai_provider,
        "max_marks_map": parse_max_marks_map(payload.rubric_text),
        "created_by": current["email"],
        "created_at": now,
        "updated_at": now,
    }
    await db.sessions.insert_one(session_doc)
    return SessionResponse(**session_doc)


@api_router.get("/sessions", response_model=List[SessionResponse])
async def list_sessions(current: Dict = Depends(get_current_instructor)) -> List[SessionResponse]:
    rows = await db.sessions.find({"created_by": current["email"]}, {"_id": 0}).sort("updated_at", -1).to_list(200)
    return [SessionResponse(**row) for row in rows]


@api_router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str, current: Dict = Depends(get_current_instructor)) -> SessionResponse:
    session_doc = await db.sessions.find_one({"id": session_id}, {"_id": 0})
    if not session_doc:
        raise HTTPException(status_code=404, detail="Session not found")
    _validate_owner(session_doc, current["email"])
    return SessionResponse(**session_doc)


@api_router.put("/sessions/{session_id}/model", response_model=SessionResponse)
async def update_model(session_id: str, payload: ModelChoiceRequest, current: Dict = Depends(get_current_instructor)) -> SessionResponse:
    session_doc = await db.sessions.find_one({"id": session_id}, {"_id": 0})
    if not session_doc:
        raise HTTPException(status_code=404, detail="Session not found")
    _validate_owner(session_doc, current["email"])
    await db.sessions.update_one(
        {"id": session_id},
        {"$set": {"ai_provider": payload.ai_provider, "updated_at": utcnow()}},
    )
    updated = await db.sessions.find_one({"id": session_id}, {"_id": 0})
    return SessionResponse(**updated)


async def _upsert_job(job: Dict) -> None:
    JOBS[job["id"]] = job
    await db.jobs.update_one({"id": job["id"]}, {"$set": job}, upsert=True)


def _new_job(session_id: str, job_type: str, total_items: int, message: str) -> Dict:
    now = utcnow()
    return {
        "id": str(uuid.uuid4()),
        "session_id": session_id,
        "job_type": job_type,
        "status": "queued",
        "progress_percent": 0.0,
        "total_items": total_items,
        "processed_items": 0,
        "failed_items": 0,
        "message": message,
        "errors": [],
        "created_at": now,
        "updated_at": now,
    }


async def _process_upload_job(job_id: str, session_doc: Dict, files_payload: List[Dict]) -> None:
    job = JOBS[job_id]
    job["status"] = "running"
    job["message"] = "Processing uploaded files"
    await _upsert_job(job)

    for index, uploaded in enumerate(files_payload):
        try:
            expanded_docs = expand_submission_file(uploaded["filename"], uploaded["content"])
            for source_name, raw_text in expanded_docs:
                extracted = await extract_student_information(
                    raw_text,
                    session_doc.get("question_paper_text", ""),
                )
                now = utcnow()
                submission = {
                    "id": str(uuid.uuid4()),
                    "session_id": session_doc["id"],
                    "filename": source_name,
                    "source_filename": uploaded["filename"],
                    "student_name": extracted["student_name"],
                    "roll_number": extracted["roll_number"],
                    "answers": extracted["answers"],
                    "extraction_flags": extracted["extraction_flags"],
                    "grading": [],
                    "total_score": 0.0,
                    "plagiarism_flag": False,
                    "plagiarism_score": 0.0,
                    "plagiarism_matches": [],
                    "review_note": None,
                    "ai_provider_used": None,
                    "status": "uploaded",
                    "created_at": now,
                    "updated_at": now,
                }
                await db.submissions.insert_one(submission)
        except Exception as exc:
            job["failed_items"] += 1
            job["errors"].append(f"{uploaded['filename']}: {str(exc)}")

        job["processed_items"] = index + 1
        job["progress_percent"] = round((job["processed_items"] / max(job["total_items"], 1)) * 100, 2)
        job["updated_at"] = utcnow()
        await _upsert_job(job)

    job["status"] = "completed"
    job["message"] = "Upload processing completed"
    job["updated_at"] = utcnow()
    await _upsert_job(job)


@api_router.post("/sessions/{session_id}/bulk-upload", response_model=JobResponse)
async def bulk_upload(
    session_id: str,
    files: List[UploadFile] = File(...),
    current: Dict = Depends(get_current_instructor),
) -> JobResponse:
    session_doc = await db.sessions.find_one({"id": session_id}, {"_id": 0})
    if not session_doc:
        raise HTTPException(status_code=404, detail="Session not found")
    _validate_owner(session_doc, current["email"])

    files_payload: List[Dict] = []
    for item in files:
        if not is_allowed_file(item.filename):
            raise HTTPException(status_code=400, detail=f"Unsupported format: {item.filename}")
        content = await item.read()
        if len(content) > MAX_FILE_SIZE_MB * 1024 * 1024:
            raise HTTPException(status_code=400, detail=f"{item.filename} exceeds {MAX_FILE_SIZE_MB} MB")
        files_payload.append({"filename": item.filename, "content": content})

    job = _new_job(session_id=session_id, job_type="upload", total_items=len(files_payload), message="Upload queued")
    await _upsert_job(job)
    asyncio.create_task(_process_upload_job(job["id"], session_doc, files_payload))
    return JobResponse(**job)


async def _process_grading_job(job_id: str, session_doc: Dict, ai_provider: str) -> None:
    job = JOBS[job_id]
    job["status"] = "running"
    job["message"] = f"Grading submissions using {ai_provider}"
    await _upsert_job(job)

    submissions = await db.submissions.find({"session_id": session_doc["id"]}, {"_id": 0}).to_list(2000)

    for index, submission in enumerate(submissions):
        try:
            grading_output = await grade_answers(
                answers=submission.get("answers", {}),
                answer_key_text=session_doc["answer_key_text"],
                rubric_text=session_doc["rubric_text"],
                max_marks_map=session_doc.get("max_marks_map", {}),
                ai_provider=ai_provider,
            )
            await db.submissions.update_one(
                {"id": submission["id"]},
                {
                    "$set": {
                        "grading": grading_output["grading"],
                        "total_score": grading_output["total_score"],
                        "ai_provider_used": ai_provider,
                        "status": "graded",
                        "updated_at": utcnow(),
                    }
                },
            )
        except Exception as exc:
            job["failed_items"] += 1
            job["errors"].append(f"{submission['id']}: {str(exc)}")
            await db.submissions.update_one(
                {"id": submission["id"]},
                {"$set": {"status": "error", "review_note": str(exc), "updated_at": utcnow()}},
            )

        job["processed_items"] = index + 1
        job["progress_percent"] = round((job["processed_items"] / max(job["total_items"], 1)) * 100, 2)
        job["updated_at"] = utcnow()
        await _upsert_job(job)

    graded = await db.submissions.find({"session_id": session_doc["id"], "status": {"$in": ["graded", "reviewed", "approved"]}}, {"_id": 0}).to_list(2000)
    plagiarism_map = calculate_plagiarism_flags(graded)
    for submission in graded:
        plagiarism = plagiarism_map.get(submission["id"], {})
        await db.submissions.update_one(
            {"id": submission["id"]},
            {
                "$set": {
                    "plagiarism_flag": plagiarism.get("plagiarism_flag", False),
                    "plagiarism_score": plagiarism.get("plagiarism_score", 0.0),
                    "plagiarism_matches": plagiarism.get("plagiarism_matches", []),
                    "updated_at": utcnow(),
                }
            },
        )

    job["status"] = "completed"
    job["message"] = "Grading and plagiarism analysis completed"
    job["updated_at"] = utcnow()
    await _upsert_job(job)


@api_router.post("/sessions/{session_id}/grade", response_model=JobResponse)
async def grade_session(
    session_id: str,
    payload: GradeJobRequest,
    current: Dict = Depends(get_current_instructor),
) -> JobResponse:
    session_doc = await db.sessions.find_one({"id": session_id}, {"_id": 0})
    if not session_doc:
        raise HTTPException(status_code=404, detail="Session not found")
    _validate_owner(session_doc, current["email"])

    total_items = await db.submissions.count_documents({"session_id": session_id})
    if total_items == 0:
        raise HTTPException(status_code=400, detail="No submissions uploaded yet")

    ai_provider = payload.ai_provider or session_doc.get("ai_provider", "gemini")
    job = _new_job(session_id=session_id, job_type="grading", total_items=total_items, message="Grading queued")
    await _upsert_job(job)
    asyncio.create_task(_process_grading_job(job["id"], session_doc, ai_provider))
    return JobResponse(**job)


@api_router.get("/jobs/{job_id}", response_model=JobResponse)
async def job_status(job_id: str, current: Dict = Depends(get_current_instructor)) -> JobResponse:
    job = JOBS.get(job_id)
    if not job:
        job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    session_doc = await db.sessions.find_one({"id": job["session_id"]}, {"_id": 0})
    if not session_doc:
        raise HTTPException(status_code=404, detail="Session not found")
    _validate_owner(session_doc, current["email"])
    return JobResponse(**job)


@api_router.get("/sessions/{session_id}/submissions", response_model=List[SubmissionResponse])
async def list_submissions(session_id: str, current: Dict = Depends(get_current_instructor)) -> List[SubmissionResponse]:
    session_doc = await db.sessions.find_one({"id": session_id}, {"_id": 0})
    if not session_doc:
        raise HTTPException(status_code=404, detail="Session not found")
    _validate_owner(session_doc, current["email"])

    rows = await db.submissions.find({"session_id": session_id}, {"_id": 0}).sort("created_at", 1).to_list(5000)
    return [SubmissionResponse(**row) for row in rows]


@api_router.put("/submissions/{submission_id}/manual-review", response_model=SubmissionResponse)
async def manual_review(
    submission_id: str,
    payload: ManualReviewRequest,
    current: Dict = Depends(get_current_instructor),
) -> SubmissionResponse:
    submission = await db.submissions.find_one({"id": submission_id}, {"_id": 0})
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    session_doc = await db.sessions.find_one({"id": submission["session_id"]}, {"_id": 0})
    if not session_doc:
        raise HTTPException(status_code=404, detail="Session not found")
    _validate_owner(session_doc, current["email"])

    total_score = round(sum(item.score for item in payload.grading), 2)
    status = "approved" if payload.approved else "reviewed"
    updated_fields = {
        "grading": [line.model_dump() for line in payload.grading],
        "total_score": total_score,
        "review_note": payload.review_note,
        "status": status,
        "updated_at": utcnow(),
    }
    await db.submissions.update_one({"id": submission_id}, {"$set": updated_fields})
    updated = await db.submissions.find_one({"id": submission_id}, {"_id": 0})
    return SubmissionResponse(**updated)


@api_router.get("/sessions/{session_id}/analytics")
async def analytics(session_id: str, current: Dict = Depends(get_current_instructor)) -> Dict:
    session_doc = await db.sessions.find_one({"id": session_id}, {"_id": 0})
    if not session_doc:
        raise HTTPException(status_code=404, detail="Session not found")
    _validate_owner(session_doc, current["email"])

    rows = await db.submissions.find({"session_id": session_id, "status": {"$in": ["graded", "reviewed", "approved"]}}, {"_id": 0}).to_list(5000)
    if not rows:
        return {
            "average": 0,
            "highest": 0,
            "lowest": 0,
            "distribution": [],
            "question_difficulty": [],
            "total_submissions": 0,
        }

    scores = [item.get("total_score", 0) for item in rows]
    average = round(sum(scores) / max(len(scores), 1), 2)
    highest = max(scores)
    lowest = min(scores)

    bins = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    distribution = []
    for index, (start, end) in enumerate(zip(bins, bins[1:])):
        if index == len(bins) - 2:
            count = len([s for s in scores if start <= s <= end])
        else:
            count = len([s for s in scores if start <= s < end])
        distribution.append({"range": f"{start}-{end}", "count": count})

    question_totals: Dict[str, Dict[str, float]] = {}
    for row in rows:
        for q in row.get("grading", []):
            qid = q["question_id"]
            if qid not in question_totals:
                question_totals[qid] = {"score_sum": 0.0, "max_sum": 0.0, "count": 0}
            question_totals[qid]["score_sum"] += float(q.get("score", 0.0))
            question_totals[qid]["max_sum"] += float(q.get("max_marks", 0.0))
            question_totals[qid]["count"] += 1

    difficulty = []
    for qid, values in sorted(question_totals.items()):
        avg_percent = (values["score_sum"] / max(values["max_sum"], 1.0)) * 100
        difficulty.append({"question": qid, "average_percent": round(avg_percent, 2), "difficulty": round(100 - avg_percent, 2)})

    return {
        "average": average,
        "highest": highest,
        "lowest": lowest,
        "distribution": distribution,
        "question_difficulty": difficulty,
        "total_submissions": len(rows),
    }


@api_router.get("/sessions/{session_id}/export")
async def export_grades(session_id: str, current: Dict = Depends(get_current_instructor)) -> FileResponse:
    session_doc = await db.sessions.find_one({"id": session_id}, {"_id": 0})
    if not session_doc:
        raise HTTPException(status_code=404, detail="Session not found")
    _validate_owner(session_doc, current["email"])

    rows = await db.submissions.find({"session_id": session_id}, {"_id": 0}).to_list(5000)
    if not rows:
        raise HTTPException(status_code=400, detail="No submissions available")

    question_ids = sorted({q["question_id"] for row in rows for q in row.get("grading", [])})
    export_rows = []
    for item in rows:
        row = {
            "Roll Number": item.get("roll_number", "UNKNOWN"),
            "Student Name": item.get("student_name", "Unknown Student"),
        }
        question_scores = {q["question_id"]: q.get("score", 0) for q in item.get("grading", [])}
        for qid in question_ids:
            row[qid] = question_scores.get(qid, 0)
        row["Total"] = item.get("total_score", 0)
        export_rows.append(row)

    dataframe = pd.DataFrame(export_rows)
    temp = NamedTemporaryFile(delete=False, suffix=".xlsx")
    dataframe.to_excel(temp.name, index=False)
    file_path = Path(temp.name)

    safe_title = session_doc["title"].replace(" ", "_")
    return FileResponse(
        temp.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"{safe_title}_grades.xlsx",
        background=BackgroundTask(lambda: file_path.unlink(missing_ok=True)),
    )


@api_router.get("/sessions/{session_id}/plagiarism")
async def plagiarism_report(session_id: str, current: Dict = Depends(get_current_instructor)) -> Dict:
    session_doc = await db.sessions.find_one({"id": session_id}, {"_id": 0})
    if not session_doc:
        raise HTTPException(status_code=404, detail="Session not found")
    _validate_owner(session_doc, current["email"])

    rows = await db.submissions.find({"session_id": session_id}, {"_id": 0}).to_list(5000)
    flagged = [
        {
            "submission_id": item["id"],
            "student_name": item["student_name"],
            "roll_number": item["roll_number"],
            "plagiarism_score": item.get("plagiarism_score", 0),
            "matches": item.get("plagiarism_matches", []),
        }
        for item in rows
        if item.get("plagiarism_flag")
    ]
    return {"flagged_count": len(flagged), "flagged_submissions": flagged}


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve React frontend static assets
if FRONTEND_BUILD.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_BUILD / "static")), name="static")

    @app.get("/health")
    async def health() -> Dict[str, str]:
        return {"status": "ok"}

    @app.get("/{full_path:path}", response_class=HTMLResponse)
    async def serve_react(full_path: str) -> HTMLResponse:
        index_file = FRONTEND_BUILD / "index.html"
        return HTMLResponse(content=index_file.read_text(), status_code=200)
else:
    @app.get("/health")
    async def health() -> Dict[str, str]:
        return {"status": "ok", "note": "frontend build not found"}


@app.on_event("shutdown")
async def shutdown_db_client() -> None:
    client.close()
