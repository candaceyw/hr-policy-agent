# One image, two Railway services. They differ only in the start command:
#   web  (default):  uvicorn hr_agent.web.app:app --host 0.0.0.0 --port $PORT
#   mcp  (override):  python -m hr_agent.mcp_server --http --port $PORT
# See deployed.md.

# ---------- build the React SPA ----------
FROM node:20-slim AS spa
WORKDIR /spa
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---------- python runtime ----------
FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# deps first (pinned) so this layer caches across code changes
COPY requirements.txt ./
RUN pip install -r requirements.txt

# the package itself (deps already satisfied). Editable so hr_agent stays at
# /app/src/hr_agent/ -- the code locates its data with paths relative to the
# package (parents[2] == /app), which a copy into site-packages would break.
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --no-deps -e .

# runtime data: committed vector index + corpus + mock data + built SPA,
# all under /app so parents[2] / "data" | "corpus" | "mock_data" resolve.
COPY data/ ./data/
COPY corpus/ ./corpus/
COPY mock_data/ ./mock_data/
COPY --from=spa /spa/dist ./frontend/dist

ENV STATIC_DIR=/app/frontend/dist
EXPOSE 8000
CMD ["sh", "-c", "uvicorn hr_agent.web.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
