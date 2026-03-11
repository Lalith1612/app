# AI Engine Module

This module is represented in the backend by:

- `backend/grading_engine.py` for Gemini + local model grading
- `backend/plagiarism_engine.py` for similarity checks
- `backend/document_processing.py` for extraction and parsing

It supports:

- RAG-style context retrieval from answer key + rubric
- Provider switching (`gemini` / `local`) per grading session
- Structured grading output for manual review and export
