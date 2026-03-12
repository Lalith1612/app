import json
import os
import re
import uuid
from typing import Dict, List

import httpx
import google.generativeai as genai


def parse_max_marks_map(rubric_text: str) -> Dict[str, float]:
    max_marks_map: Dict[str, float] = {}
    matches = re.findall(r"(?i)(Q\d+)\s*[:\-]?.*?(\d+(?:\.\d+)?)\s*(?:marks?|points?)", rubric_text)
    for question_id, marks in matches:
        max_marks_map[question_id.upper()] = float(marks)
    return max_marks_map


def _extract_relevant_context(question_id: str, answer_key_text: str, rubric_text: str) -> str:
    lines = (answer_key_text + "\n" + rubric_text).splitlines()
    bucket = [line for line in lines if question_id.lower() in line.lower()]
    if bucket:
        return "\n".join(bucket[:20])
    return (answer_key_text + "\n\n" + rubric_text)[:3500]


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

    fallback_match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if fallback_match:
        try:
            parsed = json.loads(fallback_match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    return {}


def _keyword_score(student_answer: str, answer_key: str, max_marks: float) -> Dict:
    key_tokens = [w.lower() for w in re.findall(r"[A-Za-z]{4,}", answer_key)]
    answer_tokens = {w.lower() for w in re.findall(r"[A-Za-z]{4,}", student_answer)}

    if not key_tokens:
        score = max_marks * 0.5 if len(student_answer) > 80 else 0.0
        return {"score": round(score, 2), "reason": "Fallback local heuristic used due missing key tokens."}

    important = set(key_tokens[:30])
    overlap = len(important.intersection(answer_tokens))
    ratio = overlap / max(1, len(important))
    score = min(max_marks, max_marks * min(1.0, ratio * 1.35))
    return {"score": round(score, 2), "reason": "Scored using local keyword overlap fallback due model response issue."}


def _build_prompt(question_id: str, max_marks: float, student_answer: str, context: str) -> str:
    return f"""Grade this student answer.
Question ID: {question_id}
Max Marks: {max_marks}
Student Answer:
{student_answer}

Reference Context (RAG from answer key + rubric):
{context}

Return strict JSON only:
{{"score": number, "reason": "short explanation"}}
"""


async def _grade_with_gemini(prompt: str) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        system_instruction="You are a strict but fair grading assistant. Return exact JSON only.",
    )
    response = model.generate_content(prompt)
    return response.text


async def _grade_with_local_model(prompt: str) -> str:
    base_url = os.environ.get("OLLAMA_URL")
    local_model = os.environ.get("LOCAL_MODEL_NAME")
    if not base_url or not local_model:
        raise RuntimeError("OLLAMA_URL and LOCAL_MODEL_NAME must be configured for local grading")
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            f"{base_url}/api/generate",
            json={"model": local_model, "prompt": prompt, "stream": False},
        )
        response.raise_for_status()
        payload = response.json()
        return payload.get("response", "{}")


async def grade_answers(
    answers: Dict[str, str],
    answer_key_text: str,
    rubric_text: str,
    max_marks_map: Dict[str, float],
    ai_provider: str,
) -> Dict:
    grading_rows = []
    total = 0.0

    for question_id, student_answer in answers.items():
        qid = question_id.upper()
        max_marks = max_marks_map.get(qid, 5.0)
        context = _extract_relevant_context(qid, answer_key_text, rubric_text)
        prompt = _build_prompt(qid, max_marks, student_answer[:4500], context)

        try:
            if ai_provider == "local":
                raw = await _grade_with_local_model(prompt)
            else:
                raw = await _grade_with_gemini(prompt)
            parsed = _safe_json_extract(raw)
            score = float(parsed.get("score", 0.0))
            reason = str(parsed.get("reason", "No explanation returned."))
            model_result = {"score": min(max(score, 0.0), max_marks), "reason": reason}
        except Exception:
            model_result = _keyword_score(student_answer, context, max_marks)

        row = {
            "question_id": qid,
            "score": round(float(model_result["score"]), 2),
            "max_marks": max_marks,
            "reason": str(model_result["reason"]),
        }
        grading_rows.append(row)
        total += float(row["score"])

    return {"grading": grading_rows, "total_score": round(total, 2)}
