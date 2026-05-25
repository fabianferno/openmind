# openmind API (FastAPI sidecar over the agent engine).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

WORKDIR /app

# deps first for layer caching
COPY pyproject.toml README.md ./
COPY agent ./agent
RUN pip install --upgrade pip && pip install .

# bundle schema + any committed seeds (DB itself is created at boot)
COPY tools ./tools
COPY data/seeds ./data/seeds

RUN mkdir -p data logs && python -m agent init-db

EXPOSE 8000
# Render/railway inject $PORT; default to 8000 locally.
CMD ["sh", "-c", "uvicorn agent.api.server:app --host 0.0.0.0 --port ${PORT:-8000}"]
