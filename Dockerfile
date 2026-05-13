FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DOSSIER_DEMO_MODE=true \
    DOSSIER_MODEL_PROVIDER=gemini \
    DOSSIER_LOCAL_MODEL_ENABLED=false \
    DOSSIER_GEMINI_ENABLED=true \
    DOSSIER_GEMINI_API_KEY_ENV=GEMINI_API_KEY \
    DOSSIER_GEMINI_MODEL=gemini-2.5-pro \
    DOSSIER_GEMINI_API_BASE_URL=https://generativelanguage.googleapis.com/v1beta \
    DOSSIER_EXTERNAL_SOURCE_MODE=live_prefer

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY ui ./ui
COPY sample_dossiers ./sample_dossiers
COPY state ./state
COPY synthetic_dossier_dataset_realistic_v2 ./synthetic_dossier_dataset_realistic_v2

RUN pip install --upgrade pip && pip install -e .

EXPOSE 7860

CMD ["sh", "-c", "uvicorn dossier_review_ai_assistant.api:app --host 0.0.0.0 --port ${PORT:-7860}"]
