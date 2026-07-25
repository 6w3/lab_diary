# Lab Diary — personal laboratory diary (lab.behejsrdcem.cz)

Osobní laboratorní deník: odběry, podmínky, upload reportů, OCR, strukturované výsledky, trendy.

**Disclaimer:** osobní deník, ne zdravotní služba / ne diagnóza.

## Stack

- FastAPI + Jinja2 + HTMX + Chart.js
- MariaDB + SQLAlchemy 2 + Alembic
- Brevo (e-mail verify)
- Classic extract: PDF text (`pdfplumber`) → RapidOCR (optional) → Tesseract + preprocess
- Smart extract (optional): NVIDIA NIM vision (`NVIDIA_API_KEY`)
- Google / Apple OAuth (optional, via env)

## Extract modes

| Mode | Where | Notes |
|------|--------|--------|
| **Classic** | VPS | free, data stays local |
| **Smart** | NVIDIA NIM | needs consent; better for photos / multi-date tables |

Set in `.env`: `NVIDIA_API_KEY`, `SMART_MODEL=nvidia/nemotron-3-nano-omni-30b-a3b-reasoning`, `OCR_ENGINE=auto|rapid|tesseract`.

Optional RapidOCR: `pip install 'lab-diary[ocr-rapid]'`.

Eval NVIDIA models: `python scripts/eval_nvidia_models.py`

## Local run

```bash
cp .env.example .env
# fill SECRET_KEY and optionally BREVO_API_KEY / NVIDIA_API_KEY
docker compose up --build
```

App: http://localhost:8000  
Health: http://localhost:8000/health

Without Brevo key, verification links are logged to the app container stdout (`DEV_LOG_EMAIL=true`).

## Deploy (VPS)

App is built from this repo as a git submodule at `vps/services/lab_diary`.

```bash
# from vps repo, when ready (do not run unless intentional):
./run.sh conf.yml start prod lab_diary_db lab_diary
```

Domain: `https://lab.behejsrdcem.cz`

Persist uploads at `/vps/data/lab_diary_uploads`, DB at `/vps/data/lab_diary_db`. Put `NVIDIA_API_KEY` in compose env (not git).
