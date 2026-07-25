# Lab Diary — agent instructions

Personal lab diary app (`lab.behejsrdcem.cz`). Repo: `git@github.com:6w3/lab_diary.git`.

## Maintain these docs

When the user gives **durable** process/product instructions (deploy, scope, units, Smart, language, …), write them here and/or in `.cursor/rules/`.

- Prefer **AGENTS.md** for detail; keep `.cursor/rules/*.mdc` short (essentials + pointer here).
- **Keep files lean**: merge/update outdated bullets; do not stack duplicates or one-off chat noise.
- Include this maintenance rule itself whenever relevant long-term prefs are added.

## Language & scope

- Reply in **Czech**; code/comments/commits in **English**.
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
- Smart provider = **NVIDIA NIM only** (no paid Gemini/etc. unless user asks).

## Units & marker bind

- Quantity groups: `UNIT_GROUPS` + `MARKER_UNIT_GROUP` in `app/services/units.py`. Review unit select = **that group only** (custom → full `UNIT_CHOICES`). Detected unit outside group stays as extra option (no silent rewrite).
- **Persist** report/review unit (normalize string only). Do **not** force `to_canonical` on confirm.
- **Magnitude unit fix**: if Smart labels HGB/MCHC as `g/l` but value+refs are clearly `g/dl` scale (e.g. 13.5 / 12–16), `correct_unit_by_magnitude` rewrites the unit label only (no rescale) on enrich + confirm.
- **Trends** / compare: `to_canonical` → marker `default_unit`.
- Fraction (HCT/RDW): `l`/`l/l` → unit `1`; group `["%", "1"]`; value unchanged on unit normalize.
- Bind priority: valid Smart `marker_code` → LIS brackets (`[HGB]`, …) / `GMT`→`ggt` → user alias → fuzzy. Smart gaps use fuzzy (no custom flood).

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

**Progressive import**:
1. **Soubory** (`/import/{id}/progress`) — per-file preview + read-only biomarkers, re-extract/delete; **Done, hide** collapses verified cards (localStorage per job) so user focuses on failures/odd ones; continue mid-flight OK.
2. **Odběry** (`/import/{id}/review`) — merge by date, edit/confirm. Back link to Soubory.
Confirm drops by proposal `uid`. After conditions wizard, return via `import_continue_url`.

**Trends**: charts + table + **Analýza** tab — NVIDIA text summary of all confirmed results (lab/tip refs + draw conditions). Button + consent; session-cached text; educational only (**not** a diagnosis).

Smart extract:

- Schema examples must stay **placeholders** (never real ferritin/0.0 examples — VLMs copy them).
- Date discovery must classify `single` vs `multi_column`; never force consecutive calendar-day spam.
- **Lab results gate**: Smart first classifies `doc_kind` — only `lab_results` (measured values+units) may emit biomarkers. Žádanka / other non-result docs → `not_lab_results`, empty draws.
- Discard / retry when output looks hallucinated (one marker, many dates, all zeros).
- Never silent-fall back to classic OCR when Smart fails.
- EHR screenshots (PC DOKTOR): single draw, extract **all** visible analytes.

## Marker catalog

Extend `MARKER_SEED` + `MARKER_ALIASES` for standard Czech lab abbreviations (e.g. `Barvivo erytr. MCH` → `mch`). Also cover tumor extras (`ca72_4`, `scc`), thyroglobulin (not bare `tg`), PCT, urine dipstick / 24h metabolites (`urine_ph`, `urobilinogen`, `hiiaa`, `vma`, `bence_jones`). Never let short tokens (`k`, `ca`, `ph`) fuzzy-steal multi-word labels.
**Smart AI is the primary marker mapper** (Czech labels → catalog `marker_code`). Backend trusts a valid Smart code; LIS brackets + fuzzy fill gaps (see Units & marker bind).
