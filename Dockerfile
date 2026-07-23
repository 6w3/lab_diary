FROM python:3.12-slim-bookworm

# Stale builder base images often miss rotated Debian archive keys (NO_PUBKEY).
# Refresh keyring first, then install OCR/runtime deps.
RUN set -eux; \
    apt-get -o Acquire::AllowInsecureRepositories=true \
            -o Acquire::AllowDowngradeToInsecureRepositories=true \
            update; \
    apt-get install -y --allow-unauthenticated --no-install-recommends \
        ca-certificates \
        debian-archive-keyring; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-ces \
        tesseract-ocr-eng \
        poppler-utils \
        libheif1; \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic
COPY scripts ./scripts

RUN pip install --no-cache-dir .

RUN mkdir -p /data/uploads

ENV UPLOAD_DIR=/data/uploads
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
