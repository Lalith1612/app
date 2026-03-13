# ZenGrade — AI-Powered Assignment Grading System

> Bulk-grade student submissions with AI, detect plagiarism, review manually, and export results in seconds.

**Live Demo:** https://app-production-96c1.up.railway.app

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Architecture](#architecture)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Local Development](#local-development)
  - [Environment Variables](#environment-variables)
- [Deployment](#deployment)
  - [Railway (Recommended)](#railway-recommended)
  - [Docker](#docker)
- [API Reference](#api-reference)
- [Project Structure](#project-structure)
- [How It Works](#how-it-works)
- [Roadmap](#roadmap)
- [License](#license)

---

## Overview

ZenGrade is a production-ready web application that automates the grading of student assignments. Instructors upload an answer key and rubric, then bulk-upload student submissions (PDF, DOCX, TXT, or ZIP). The system extracts each student's answers, grades them using Google Gemini AI, detects plagiarism, and lets instructors review and approve scores before exporting a final Excel grade sheet.

---

## Features

### Core
- **JWT Authentication** — Secure instructor registration, login, and protected API routes
- **Assignment Sessions** — Organize grading by exam: upload question paper, answer key, and rubric per session
- **Bulk File Upload** — Upload PDF, DOCX, TXT, or ZIP (containing multiple files) in one go
- **AI Grading** — Gemini 1.5 Flash grades each answer against the rubric with scores and reasoning
- **Local LLM Support** — Switch to a self-hosted Ollama model per session
- **Plagiarism Detection** — TF-IDF cosine similarity flags suspicious submission pairs
- **Manual Review** — Instructors can override any score, add notes, and approve submissions
- **Analytics Dashboard** — Score distribution, average/highest/lowest, per-question difficulty charts
- **Excel Export** — One-click download of a grade sheet with per-question scores and totals

### UX
- Responsive layout (mobile, tablet, desktop)
- Dark mode with persistent toggle
- Real-time job progress polling
- Extraction flags for missing student name or roll number

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, Tailwind CSS, shadcn/ui, Recharts, react-dropzone |
| Backend | FastAPI, Uvicorn, Motor (async MongoDB) |
| Database | MongoDB Atlas |
| AI | Google Gemini 1.5 Flash (`google-generativeai`) |
| Local AI | Ollama (optional) |
| Document Parsing | PyMuPDF, pdfplumber, docx2txt |
| Plagiarism | scikit-learn TF-IDF cosine similarity |
| Export | pandas + openpyxl |
| Auth | JWT (python-jose + passlib + bcrypt) |
| Deployment | Docker (multi-stage), Railway |

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                     Railway Container                │
│                                                     │
│  ┌──────────────┐        ┌──────────────────────┐   │
│  │  React SPA   │◄──────►│   FastAPI Backend    │   │
│  │  (built,     │        │   /api/*             │   │
│  │   served by  │        │                      │   │
│  │   FastAPI)   │        │  ┌────────────────┐  │   │
│  └──────────────┘        │  │ Background Jobs│  │   │
│                          │  │ - Upload       │  │   │
│                          │  │ - Grading      │  │   │
│                          │  └────────────────┘  │   │
│                          └──────────┬───────────┘   │
└─────────────────────────────────────┼───────────────┘
                                      │
              ┌───────────────────────┼──────────────┐
              │                       │              │
     ┌────────▼──────┐    ┌──────────▼──────┐  ┌────▼────┐
     │ MongoDB Atlas  │    │  Google Gemini  │  │ Ollama  │
     │  (cloud DB)    │    │   1.5 Flash     │  │(optional│
     └────────────────┘    └─────────────────┘  └─────────┘
```

The React frontend is built at Docker image build time and served as static files by the FastAPI backend. All `/api/*` routes go to FastAPI; all other routes serve the React `index.html` for client-side routing.

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 20+
- MongoDB Atlas account (free tier works)
- Google Gemini API key ([get one here](https://aistudio.google.com/app/apikey))
- Docker (for containerized run)

### Local Development

**1. Clone the repository**

```bash
git clone https://github.com/your-username/zengrade.git
cd zengrade
```

**2. Set up the backend**

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**3. Configure environment variables**

Create `backend/.env`:

```env
MONGO_URL=mongodb+srv://username:password@cluster0.xxxxx.mongodb.net/?appName=Cluster0
DB_NAME=zengrade
JWT_SECRET=your-super-secret-jwt-key-change-this
GEMINI_API_KEY=your-gemini-api-key
CORS_ORIGINS=http://localhost:3000
```

**4. Start the backend**

```bash
cd backend
uvicorn server:app --reload --port 8001
```

**5. Set up and start the frontend**

```bash
cd frontend
cp .env.example .env          # or create .env manually
# Set REACT_APP_BACKEND_URL=http://localhost:8001 in .env
yarn install
yarn start
```

The app will be available at `http://localhost:3000`.

### Environment Variables

| Variable | Required | Description |
|---|---|---|
| `MONGO_URL` | ✅ | MongoDB connection string (Atlas `mongodb+srv://...`) |
| `DB_NAME` | ✅ | Database name (e.g. `zengrade`) |
| `JWT_SECRET` | ✅ | Secret key for signing JWT tokens — use a long random string |
| `GEMINI_API_KEY` | ✅ | Google Gemini API key |
| `CORS_ORIGINS` | ✅ | Allowed frontend origins (use `*` to allow all) |
| `REACT_APP_BACKEND_URL` | ✅ (build-time) | Public URL of the backend — baked into the React build |
| `PORT` | ⬜ | Port to run on (Railway sets this automatically, defaults to `8001`) |
| `OLLAMA_URL` | ⬜ | Base URL of local Ollama instance (e.g. `http://localhost:11434`) |
| `LOCAL_MODEL_NAME` | ⬜ | Ollama model name (e.g. `qwen2.5:3b-instruct`) |
| `PLAGIARISM_THRESHOLD` | ⬜ | Cosine similarity threshold for flagging (default `0.88`) |

---

## Deployment

### Railway (Recommended)

1. Push your code to GitHub
2. Create a new Railway project → **Deploy from GitHub repo**
3. Railway auto-detects the `Dockerfile`
4. Go to your service → **Variables** and add all required environment variables (see table above)
5. Add `REACT_APP_BACKEND_URL` as both a **Variable** and a **Build Argument** (Railway build args panel) — set it to your Railway public URL, e.g. `https://your-app.up.railway.app`
6. Railway will build and deploy automatically

**MongoDB Atlas setup:**
1. Create a free M0 cluster at [mongodb.com/cloud/atlas](https://mongodb.com/cloud/atlas)
2. Create a database user with a password (use letters + numbers only, no special characters)
3. Under **Network Access**, add `0.0.0.0/0` to allow connections from Railway
4. Copy the connection string and set it as `MONGO_URL` in Railway

### Docker

**Build and run locally:**

```bash
docker build \
  --build-arg REACT_APP_BACKEND_URL=http://localhost:8001 \
  -t zengrade .

docker run -p 8001:8001 \
  -e MONGO_URL="mongodb+srv://..." \
  -e DB_NAME="zengrade" \
  -e JWT_SECRET="your-secret" \
  -e GEMINI_API_KEY="your-key" \
  zengrade
```

Open `http://localhost:8001`.

**Docker Compose (with local MongoDB):**

```bash
docker-compose up --build
```

---

## API Reference

All endpoints are prefixed with `/api`.

### Authentication

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/auth/register` | Register a new instructor |
| `POST` | `/api/auth/login` | Login and receive JWT token |
| `GET` | `/api/auth/me` | Get current instructor profile |

### Sessions

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/sessions` | Create a new grading session |
| `GET` | `/api/sessions` | List all sessions for current instructor |
| `GET` | `/api/sessions/{id}` | Get session details |
| `PUT` | `/api/sessions/{id}/model` | Switch AI provider for a session |

### Submissions & Jobs

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/sessions/{id}/bulk-upload` | Upload student submission files |
| `POST` | `/api/sessions/{id}/grade` | Start AI grading job |
| `GET` | `/api/jobs/{job_id}` | Poll job progress |
| `GET` | `/api/sessions/{id}/submissions` | List all submissions in a session |
| `PUT` | `/api/submissions/{id}/manual-review` | Override scores and approve |

### Analytics & Export

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/sessions/{id}/analytics` | Score distribution and difficulty stats |
| `GET` | `/api/sessions/{id}/export` | Download Excel grade sheet |
| `GET` | `/api/sessions/{id}/plagiarism` | Get plagiarism report |

**Authentication:** All endpoints (except `/auth/register` and `/auth/login`) require a `Bearer` token in the `Authorization` header.

---

## Project Structure

```
zengrade/
├── Dockerfile                  # Multi-stage build (Node + Python)
├── docker-compose.yml          # Local dev with MongoDB
├── .dockerignore
│
├── backend/
│   ├── server.py               # FastAPI app, all routes
│   ├── auth_utils.py           # JWT creation, verification, password hashing
│   ├── document_processing.py  # PDF/DOCX/TXT parsing, student info extraction
│   ├── grading_engine.py       # AI grading logic (Gemini + Ollama fallback)
│   ├── plagiarism_engine.py    # TF-IDF cosine similarity plagiarism detection
│   ├── schemas.py              # Pydantic request/response models
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── App.js
│   │   ├── pages/
│   │   │   ├── LoginPage.jsx
│   │   │   ├── DashboardPage.jsx
│   │   │   ├── NewSessionPage.jsx
│   │   │   └── SessionDetailPage.jsx
│   │   ├── components/
│   │   │   ├── AppShell.jsx
│   │   │   ├── MetricCard.jsx
│   │   │   └── ui/             # shadcn/ui components
│   │   ├── context/
│   │   │   ├── AuthContext.jsx
│   │   │   └── ThemeContext.jsx
│   │   └── lib/
│   │       └── api.js          # Axios API client
│   └── package.json
│
└── memory/
    └── PRD.md                  # Product Requirements Document
```

---

## How It Works

### 1. Create a Session
Instructor creates a session with the exam's question paper text, answer key, and rubric. The rubric is parsed to extract per-question maximum marks.

### 2. Upload Submissions
Instructor uploads student files (PDF, DOCX, TXT, or ZIP bundles). A background job processes each file:
- Extracts raw text using PyMuPDF + pdfplumber (PDF) or docx2txt (DOCX)
- Runs regex patterns to detect student name, roll number, and answer blocks (Q1, Q2, etc.)
- Falls back to Gemini AI extraction if regex can't confidently parse the structure

### 3. AI Grading
A second background job grades each submission:
- For each answer, builds a prompt with the rubric context and student answer
- Sends to Gemini 1.5 Flash (or local Ollama model) and parses JSON `{score, reason}`
- Falls back to keyword overlap scoring if the AI call fails
- Runs plagiarism detection (TF-IDF cosine similarity) across all graded submissions

### 4. Review & Export
- Instructor reviews AI scores, reads reasoning, and can override any score
- Marks submissions as approved
- Exports a full Excel grade sheet with per-question columns and totals

---

## Roadmap

### In Progress
- [ ] WebSocket real-time progress (replace polling)
- [ ] Robust PDF answer segmentation for tables and complex layouts

### Planned
- [ ] Session cloning for repeated exams
- [ ] Bulk correction tools for missing student info
- [ ] Side-by-side plagiarism comparison view
- [ ] PDF summary report download
- [ ] Email notifications on grading completion
- [ ] Pagination and search for large submission datasets
- [ ] Audit log for score overrides and approvals
- [ ] Multi-course and term filtering

---

## License

MIT License — see [LICENSE](LICENSE) for details.
