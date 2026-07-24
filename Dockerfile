FROM python:3.12-alpine

# Root cause on this VPS builder:
# 1) Debian slim apt fails (rotated archive keys)
# 2) Bootstrapping keyring via dpkg hits lzma "Cannot allocate memory"
#    under host cgroup RAM pressure — tesseract apt install would too.
# Alpine + apk avoids both. Pure Python deps install from musllinux wheels
# (no gcc), so the build stays light on RAM.
RUN apk add --no-cache \
    tesseract-ocr \
    tesseract-ocr-data-ces \
    tesseract-ocr-data-eng \
    poppler-utils \
    libheif \
    jpeg \
    zlib \
    freetype \
    libffi \
    openssl

WORKDIR /app

COPY pyproject.toml README.md ./
COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic
COPY scripts ./scripts

RUN pip install --no-cache-dir .

RUN mkdir -p /data/uploads

ENV UPLOAD_DIR=/data/uploads
ENV OCR_ENGINE=auto
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
