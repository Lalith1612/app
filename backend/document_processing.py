import io
import json
import os
import re
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Dict, List, Tuple

import docx2txt
import fitz
import pdfplumber
from emergentintegrations.llm.chat import LlmChat, UserMessage


ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".zip"}
INNER_ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}


def is_allowed_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def _read_pdf(file_bytes: bytes) -> str:
    fitz_text = ""
    plumber_text = ""
    try:
        with fitz.open(stream=file_bytes, filetype="pdf") as doc:
            fitz_text = "\n".join([page.get_text() for page in doc]).strip()
    except Exception:
        fitz_text = ""

    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            plumber_text = "\n".join([(page.extract_text() or "") for page in pdf.pages]).strip()
    except Exception:
        plumber_text = ""

    return fitz_text if len(fitz_text) >= len(plumber_text) else plumber_text


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


def _safe_json_extract(text: str) -> Dict:
    cleaned = text.strip()
    cleaned = re.sub(r"^```json", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    return {}


def _normalize_question_key(raw_key: str) -> str:
    digits = re.findall(r"\d+", raw_key)
    if digits:
        return f"Q{int(digits[0])}"
    return re.sub(r"\s+", "", raw_key.upper())


def _extract_answers_with_patterns(normalized_text: str) -> Dict[str, str]:
    answers: Dict[str, str] = {}
    header_patterns = [
        re.compile(r"(?im)^\s*(?:q(?:uestion)?|que|ans(?:wer)?)\s*[:#\-\.]?\s*(\d{1,2})\s*[\)\].:\-]?\s*"),
        re.compile(r"(?im)^\s*(\d{1,2})\s*[\)\].\-]\s*"),
    ]

    matches = []
    for pattern in header_patterns:
        for match in pattern.finditer(normalized_text):
            question_number = int(match.group(1))
            if 1 <= question_number <= 80:
                matches.append((match.start(), match.end(), question_number))

    if not matches:
        return answers

    matches = sorted(matches, key=lambda x: x[0])
    deduped = []
    seen_starts = set()
    for item in matches:
        if item[0] in seen_starts:
            continue
        seen_starts.add(item[0])
        deduped.append(item)

    for index, (start, end, question_number) in enumerate(deduped):
        next_start = deduped[index + 1][0] if index + 1 < len(deduped) else len(normalized_text)
        question_id = f"Q{question_number}"
        answer_text = normalized_text[end:next_start].strip()
        if answer_text:
            if question_id in answers:
                answers[question_id] = f"{answers[question_id]}\n{answer_text}".strip()
            else:
                answers[question_id] = answer_text

    return answers


async def _llm_extract_student_fields(raw_text: str, question_paper_text: str = "") -> Dict:
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_key:
        return {}

    prompt = f"""
    Extract structured student submission data from the text below.

    Required JSON schema only:
    {{
      "student_name": "string",
      "roll_number": "string",
      "answers": {{"Q1": "...", "Q2": "..."}}
    }}

    Rules:
    - Roll number synonyms: Roll No, Roll Number, Reg No, Registration Number, Candidate ID, Student ID.
    - Question label variants: Q1, Question 1, Que 1, 1), (1), Ans 1.
    - If numbering is unclear, infer answer blocks logically and still map to Q1, Q2, ...
    - Return JSON only. No markdown.

    Question paper context:
    {question_paper_text[:3000]}

    Document text:
    {raw_text[:12000]}
    """

    try:
        chat = LlmChat(
            api_key=gemini_key,
            session_id=f"extract-{uuid.uuid4()}",
            system_message="You extract assignment metadata into strict JSON.",
        ).with_model("gemini", "gemini-3-flash-preview")
        response = await chat.send_message(UserMessage(text=prompt))
        parsed = _safe_json_extract(response)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


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


async def extract_student_information(raw_text: str, question_paper_text: str = "") -> Dict[str, str | Dict[str, str] | List[str]]:
    normalized = raw_text.replace("\r", "\n")
    flags: List[str] = []

    name_match = re.search(
        r"(?im)^\s*(?:student\s*name|name\s*of\s*student|candidate\s*name|name)\s*[:\-]\s*(.+)$",
        normalized,
    )
    roll_match = re.search(
        r"(?im)^\s*(?:roll\s*(?:number|no|#)?|reg(?:istration)?\s*(?:number|no|#)?|candidate\s*id|student\s*id)\s*[:\-]\s*([A-Za-z0-9][A-Za-z0-9\-_/\.\s]{0,60})$",
        normalized,
    )
    if not roll_match:
        roll_match = re.search(
            r"(?i)(?:roll\s*(?:number|no|#)?|reg(?:istration)?\s*(?:number|no|#)?|candidate\s*id|student\s*id)\s*[:\-]\s*([A-Za-z0-9][A-Za-z0-9\-_/\.\s]{0,60})",
            normalized,
        )

    student_name = name_match.group(1).strip() if name_match else "Unknown Student"
    roll_number = roll_match.group(1).strip(" .\t\n") if roll_match else "UNKNOWN"

    if student_name == "Unknown Student":
        flags.append("Student name missing")
    if roll_number == "UNKNOWN":
        flags.append("Roll number missing")

    answers = _extract_answers_with_patterns(normalized)
    if not answers:
        body = normalized.strip()
        answers = {"Q1": body[:10000]} if body else {}
        flags.append("Could not confidently detect question-wise structure with rules.")

    needs_llm_assist = (
        student_name == "Unknown Student"
        or roll_number == "UNKNOWN"
        or len(answers) == 0
        or any("Could not confidently detect question-wise structure" in flag for flag in flags)
        or (len(answers) == 1 and len(next(iter(answers.values()), "")) > 250)
    )

    if needs_llm_assist:
        llm_result = await _llm_extract_student_fields(normalized, question_paper_text)
        llm_name = str(llm_result.get("student_name", "")).strip()
        llm_roll = str(llm_result.get("roll_number", "")).strip()
        llm_answers_raw = llm_result.get("answers", {})

        if student_name == "Unknown Student" and llm_name:
            student_name = llm_name
        if roll_number == "UNKNOWN" and llm_roll:
            roll_number = llm_roll

        if isinstance(llm_answers_raw, dict):
            llm_answers = {}
            for key, value in llm_answers_raw.items():
                if not isinstance(value, str):
                    continue
                normalized_key = _normalize_question_key(str(key))
                text_value = value.strip()
                if text_value:
                    llm_answers[normalized_key] = text_value

            if llm_answers and (len(answers) <= 1):
                answers = llm_answers

        flags.append("LLM-assisted extraction applied")

    return {
        "student_name": student_name,
        "roll_number": roll_number,
        "answers": answers,
        "extraction_flags": flags,
    }
