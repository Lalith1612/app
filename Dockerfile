FROM python:3.11-slim AS backend-builder
WORKDIR /app/backend
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend /app/backend

FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json ./
RUN yarn install --network-timeout 600000 --prefer-offline
COPY frontend /app/frontend
RUN yarn build

FROM python:3.11-slim
WORKDIR /app
COPY --from=backend-builder /usr/local/lib/python3.11 /usr/local/lib/python3.11
COPY --from=backend-builder /usr/local/bin /usr/local/bin
COPY --from=backend-builder /app/backend /app/backend
COPY --from=frontend-builder /app/frontend/build /app/frontend/build
EXPOSE 8001
CMD ["python", "-m", "uvicorn", "backend.server:app", "--host", "0.0.0.0", "--port", "8001"]
