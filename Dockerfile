# FROM python:3.11-slim AS backend-builder
# WORKDIR /app/backend
# COPY backend/requirements.txt ./requirements.txt
# RUN pip install --no-cache-dir -r requirements.txt
# COPY backend /app/backend

# FROM node:20-alpine AS frontend-builder
# WORKDIR /app/frontend
# ENV NODE_OPTIONS="--max-old-space-size=256"
# COPY frontend/package.json ./
# RUN yarn install --network-timeout 600000 --prefer-offline
# COPY frontend /app/frontend
# RUN yarn build

# FROM python:3.11-slim
# WORKDIR /app
# COPY --from=backend-builder /usr/local/lib/python3.11 /usr/local/lib/python3.11
# COPY --from=backend-builder /usr/local/bin /usr/local/bin
# COPY --from=backend-builder /app/backend /app/backend
# COPY --from=frontend-builder /app/frontend/build /app/frontend/build
# EXPOSE 8001
# CMD ["python", "-m", "uvicorn", "backend.server:app", "--host", "0.0.0.0", "--port", "8001"]
# ─── Stage 1: Build frontend ───────────────────────────────────────────────
# ─── Stage 1: Build frontend ───────────────────────────────────────────────
# ─── Stage 1: Build frontend ───────────────────────────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

COPY frontend/package.json frontend/yarn.lock* ./
RUN yarn install --frozen-lockfile --network-timeout 600000

COPY frontend ./

# REACT_APP_BACKEND_URL must be passed at build time:
# In Railway → service Variables, set REACT_APP_BACKEND_URL to your Railway public URL
# e.g. https://your-app.up.railway.app
ARG REACT_APP_BACKEND_URL=""
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL

RUN yarn build

# ─── Stage 2: Final image ───────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# System deps for PyMuPDF/pdfplumber
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmupdf-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY backend /app/backend

# Copy built React frontend
COPY --from=frontend-builder /app/frontend/build /app/frontend/build

EXPOSE 8001

# Use PORT env var if Railway injects it, otherwise default to 8001
CMD ["sh", "-c", "python -m uvicorn backend.server:app --host 0.0.0.0 --port ${PORT:-8001}"]
