from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    password: str = Field(min_length=6, max_length=120)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=120)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class InstructorResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    email: EmailStr
    role: str
    created_at: datetime


class SessionCreateRequest(BaseModel):
    title: str = Field(min_length=3, max_length=150)
    question_paper_text: str = Field(min_length=10)
    answer_key_text: str = Field(min_length=10)
    rubric_text: str = Field(min_length=10)
    ai_provider: Literal["gemini", "local"] = "gemini"


class SessionResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    title: str
    question_paper_text: str
    answer_key_text: str
    rubric_text: str
    ai_provider: Literal["gemini", "local"]
    max_marks_map: Dict[str, float]
    created_by: str
    created_at: datetime
    updated_at: datetime


class ModelChoiceRequest(BaseModel):
    ai_provider: Literal["gemini", "local"]


class GradingLine(BaseModel):
    question_id: str
    score: float
    max_marks: float
    reason: str


class SubmissionResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    session_id: str
    filename: str
    source_filename: str
    student_name: str
    roll_number: str
    answers: Dict[str, str]
    extraction_flags: List[str]
    grading: List[GradingLine]
    total_score: float
    plagiarism_flag: bool
    plagiarism_score: float
    plagiarism_matches: List[Dict[str, float | str]]
    ai_provider_used: Optional[str] = None
    review_note: Optional[str] = None
    status: str
    created_at: datetime
    updated_at: datetime


class ManualReviewRequest(BaseModel):
    grading: List[GradingLine]
    approved: bool = False
    review_note: Optional[str] = None


class JobResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    session_id: str
    job_type: str
    status: str
    progress_percent: float
    total_items: int
    processed_items: int
    failed_items: int
    message: str
    errors: List[str]
    created_at: datetime
    updated_at: datetime


class GradeJobRequest(BaseModel):
    ai_provider: Optional[Literal["gemini", "local"]] = None
