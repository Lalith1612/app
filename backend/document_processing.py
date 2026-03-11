import io
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, List, Tuple

import docx2txt
import fitz
import pdfplumber


ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".zip"}
INNER_ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}


def is_allowed_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def _read_pdf(file_bytes: bytes) -> str:
    pages: List[str] = []
    try:
        with fitz.open(stream=file_bytes, filetype="pdf") as doc:
            pages = [page.get_text() for page in doc]
    except Exception:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            pages = [(page.extract_text() or "") for page in pdf.pages]
    return "\n".join(pages).strip()


def _read_docx(file_bytes: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=True) as tmp:
        tmp.write(file_bytes)
        tmp.flush()
        return docx2txt.process(tmp.name).strip()


def _read_txt(file_bytes: bytes) -> str:
    return file_bytes.decode("utf-8", errors="ignore").strip()


def extract_text_from_file(filename: str, file_bytes: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return _read_pdf(file_bytes)
    if suffix == ".docx":
        return _read_docx(file_bytes)
    if suffix == ".txt":
        return _read_txt(file_bytes)
    raise ValueError(f"Unsupported file type: {suffix}")


def expand_submission_file(filename: str, file_bytes: bytes) -> List[Tuple[str, str]]:
    suffix = Path(filename).suffix.lower()
    if suffix != ".zip":
        return [(filename, extract_text_from_file(filename, file_bytes))]

    extracted_docs: List[Tuple[str, str]] = []
    with zipfile.ZipFile(io.BytesIO(file_bytes)) as zip_ref:
        for member in zip_ref.infolist():
            if member.is_dir():
                continue
            member_suffix = Path(member.filename).suffix.lower()
            if member_suffix not in INNER_ALLOWED_EXTENSIONS:
                continue
            with zip_ref.open(member) as file_ref:
                inner_bytes = file_ref.read()
            clean_name = Path(member.filename).name
            extracted_docs.append((clean_name, extract_text_from_file(clean_name, inner_bytes)))
    return extracted_docs


def extract_student_information(raw_text: str) -> Dict[str, str | Dict[str, str] | List[str]]:
    normalized = raw_text.replace("\r", "\n")
    flags: List[str] = []

    name_match = re.search(r"(?im)^\s*(?:student\s*name|name)\s*[:\-]\s*(.+)$", normalized)
    roll_match = re.search(r"(?im)^\s*(?:roll\s*(?:number|no)?|id)\s*[:\-]\s*([A-Za-z0-9\-_/]+)$", normalized)

    student_name = name_match.group(1).strip() if name_match else "Unknown Student"
    roll_number = roll_match.group(1).strip() if roll_match else "UNKNOWN"

    if student_name == "Unknown Student":
        flags.append("Student name missing")
    if roll_number == "UNKNOWN":
        flags.append("Roll number missing")

    pattern = re.compile(
        r"(?is)(Q(?:uestion)?\s*\d+)\s*[:\-]\s*(.+?)(?=\n\s*Q(?:uestion)?\s*\d+\s*[:\-]|\Z)"
    )
    found_answers = pattern.findall(normalized)
    answers: Dict[str, str] = {}

    if found_answers:
        for question_label, answer_text in found_answers:
            question_id = re.sub(r"\s+", "", question_label.upper().replace("QUESTION", "Q"))
            answers[question_id] = answer_text.strip()
    else:
        body = normalized.strip()
        answers = {"Q1": body[:8000]}
        flags.append("Could not detect question-wise structure. Stored full text as Q1.")

    return {
        "student_name": student_name,
        "roll_number": roll_number,
        "answers": answers,
        "extraction_flags": flags,
    }
