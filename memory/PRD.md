# PRD — AI-Powered Assignment Grading System (ZenGrade)

## Original Problem Statement
Build a production-ready AI-powered Assignment Grading System as a web application that allows instructors to upload answer key/rubric + bulk student submissions, extract student details/answers, grade with AI, detect plagiarism, manually review/approve, visualize analytics, and export an Excel grade sheet.

## User Choices Captured
- Auth: JWT-based instructor authentication
- Primary AI model: Gemini 3 Flash
- API key mode: User-provided Gemini key
- File scope now: PDF, DOCX, TXT, ZIP
- Build priority: End-to-end production-style MVP
- Additional requirement: Frontend model switch between Gemini and local model

## Architecture Decisions
- Frontend: React + Tailwind + shadcn UI + Recharts + react-dropzone
- Backend: FastAPI + Motor (MongoDB)
- AI engine: Gemini via emergentintegrations; local LLM via Ollama endpoint
- Document parsing: PyMuPDF + pdfplumber + docx2txt + text parser
- Plagiarism: sentence-transformers (fallback TF-IDF cosine)
- Async workflows: background jobs for upload and grading with progress polling
- Export: Pandas/Openpyxl Excel generation
- Deployment assets: root Dockerfile + docker-compose

## User Personas
1. Instructor: creates sessions, uploads files, runs grading, reviews, exports marks.
2. Teaching Assistant: assists in manual review and final approvals.
3. Academic Coordinator: checks analytics and plagiarism flags.

## Core Requirements (Static)
- Secure instructor auth and protected APIs
- Assignment session creation (question paper, answer key, rubric)
- Bulk student upload with progress
- Student info extraction and missing-info flags
- AI grading with rubric-aware reasoning and scores
- Plagiarism detection and suspicious submission flags
- Manual review/edit/approve workflow
- Excel grade sheet export
- Analytics dashboard (distribution, averages, question difficulty)

## What’s Implemented
### 2026-03-11
- Added full-app Dark Mode with persistent theme toggle (login + app shell), root `dark` class switching, and token-based styling updates across core pages.
- Implemented JWT auth APIs: register/login/me
- Implemented session APIs: create/list/get/update model choice
- Implemented async bulk upload processing job and progress endpoint
- Added parser pipeline for PDF/DOCX/TXT/ZIP + student info extraction via regex
- Implemented AI grading job with Gemini/local model switching
- Implemented local model fallback-safe scoring when local endpoint fails
- Implemented plagiarism scoring + submission flags
- Implemented manual review/approve endpoint
- Implemented analytics endpoint with fixed inclusive 100-score bucket
- Implemented Excel export endpoint with temp-file cleanup after response
- Built full React app: login, dashboard, new session, session workspace, upload dropzone, grading controls, analytics charts, manual review UI, export
- Applied design system from `/app/design_guidelines.json` (fonts, brutalist-light style, high-contrast UI)
- Added deployment docs/modules (`ai_engine`, `database`, `deployment`)

## Prioritized Backlog
### P0
- Add robust PDF/DOCX answer segmentation for complex layouts/tables
- Add real-time WebSocket progress (instead of polling)
- Add stronger RBAC granularity (instructor/admin roles)

### P1
- Session cloning templates for repeated exams
- Bulk manual correction tools for missing roll numbers/names
- Better plagiarism evidence panel with side-by-side comparison

### P2
- Multi-course organization and term filters
- Email notifications on grading completion
- Advanced rubric editor with weighted criteria UI

## Next Tasks List
1. Add automated retry/backoff for Gemini and Ollama transient failures.
2. Add pagination and search for large submission datasets.
3. Add audit logs for score overrides and approvals.
4. Add integration tests for ZIP edge-cases and malformed files.
5. Add downloadable PDF summary report alongside Excel.
