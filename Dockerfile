FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --system --create-home reviewlens
COPY backend/app ./app
COPY --from=frontend /build/dist ./static
ENV REVIEWLENS_STATIC_DIR=/app/static \
    REVIEWLENS_CACHE=/tmp/reviewlens/analysis.sqlite3 \
    PYTHONUNBUFFERED=1
USER reviewlens
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
