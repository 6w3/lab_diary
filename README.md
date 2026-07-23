# Lab Diary — personal laboratory diary (lab.behejsrdcem.cz)

Osobní laboratorní deník: odběry, podmínky, upload reportů, OCR (Tesseract), strukturované výsledky, trendy.

**Disclaimer:** osobní deník, ne zdravotní služba / ne diagnóza.

## Stack

- FastAPI + Jinja2 + HTMX + Chart.js
- MariaDB + SQLAlchemy 2 + Alembic
- Brevo (e-mail verify)
- Tesseract OCR
- Google / Apple OAuth (optional, via env)

## Local run

```bash
cp .env.example .env
# fill SECRET_KEY and optionally BREVO_API_KEY
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
