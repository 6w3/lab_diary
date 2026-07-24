# Lab Diary — agent instructions

Personal lab diary app (`lab.behejsrdcem.cz`). Repo: `git@github.com:6w3/lab_diary.git`.

## Language & scope

- Reply to the user in **Czech**; write code/comments/commit messages in **English**.
- Do **only** what was asked. No drive-by refactors, no extra docs unless requested.
- Fix **root causes**, not symptoms.
- **Never commit or push** unless the user explicitly asks.
- Do **not** invent mock lab data when extract/API fails — fix the pipeline or collaborate on the real source.

## Product defaults

- **Upload-first**: list → “Nahrát report” (`/import`) or “Zadat ručně” (`/draws/new`).
- Default extract = **Smart NVIDIA** when `NVIDIA_API_KEY` is set (consent checked by default); Classic fallback.
- Smart must categorize markers against catalog when possible; unknown → custom marker still OK.
- Review: edit rows, **add row**, multi-draw dates, prefill **lab_name** from report when detected.
- Trends: all markers with data + tip/lab refs on one page, grouped/sorted.
- Units: fixed catalog + convert to marker `default_unit` when conversion exists.
- Smart provider = **NVIDIA NIM only** (no paid Gemini/etc. unless user asks).

## Stack (short)

FastAPI + Jinja/HTMX + Chart.js + MariaDB + Alembic. OCR classic (pdfplumber → RapidOCR/Tesseract) + Smart (`app/services/smart_extract.py`).

## Deploy / git with VPS

App is a **git submodule** of `/Users/jv/git/vps` at `services/lab_diary`.

When user asks to ship lab diary changes:

1. In `lab_diary`: commit (conventional) + `git push origin main`.
2. In `vps`: update submodule to new `lab_diary` SHA.
3. Commit in `vps` with message exactly: `update lab diary`.
4. **`git push` vps only if the only change is the `lab_diary` submodule pointer.** If other files in `vps` are dirty/changed, commit the submodule bump but **do not push** — tell the user.
5. On server (`/vps/git/vps`): `git pull`, `git submodule update --init --recursive services/lab_diary`, rebuild/restart `lab_diary` (+ DB if needed). Migrations run on container start.

Persistence on VPS: DB `/vps/data/lab_diary_db`, uploads `/vps/data/lab_diary_uploads`.

## Multi-date / import-first

Czech hospital comparison tables often use spaced dates (`14. 10. 2020 10:30`). Prefer classic multi-date table parse when it finds **more** dates than Smart.

Upload is **import-first** (`/import`): one batch can create/extend multiple draws. Never silent-merge by day+lab — review asks merge vs new draw. Files link via `draw_attachments` M2M. Dedup identical results on confirm. Conditions wizard after confirm (create new / edit existing). Split selected results on draw detail if merged by mistake.

Smart extract:
- Schema examples must stay **placeholders** (never real ferritin/0.0 examples — VLMs copy them).
- Date discovery must classify `single` vs `multi_column`; never force consecutive calendar-day spam.
- Discard / retry when output looks hallucinated (one marker, many dates, all zeros); fall back to classic.
- EHR screenshots (PC DOKTOR): single draw, extract **all** visible analytes.

## Marker catalog

Extend `MARKER_SEED` + `MARKER_ALIASES` for standard Czech lab abbreviations (e.g. `Barvivo erytr. MCH` → `mch`). Prefer Smart `marker_code` when it exists in catalog via `resolve_marker`.
