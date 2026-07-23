FROM python:3.12-slim-bookworm

# Root cause of NO_PUBKEY on builders: Debian rotated archive signing keys, but
# older python:*-slim-bookworm layers still ship debian-archive-keyring << 2025.1.
# apt cannot fetch the new keyring (chicken/egg), and "AllowInsecureRepositories"
# still exits 100 on bookworm. Install the current keyring via HTTPS + dpkg first.
RUN python - <<'PY'
from urllib.request import urlretrieve
import subprocess

url = (
    "https://deb.debian.org/debian/pool/main/d/debian-archive-keyring/"
    "debian-archive-keyring_2025.1_all.deb"
)
path = "/tmp/debian-archive-keyring.deb"
urlretrieve(url, path)
subprocess.check_call(["dpkg", "-i", path])
PY

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-ces \
        tesseract-ocr-eng \
        poppler-utils \
        libheif1 \
    && rm -rf /var/lib/apt/lists/*

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
