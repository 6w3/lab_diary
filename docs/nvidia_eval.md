# NVIDIA Smart model eval (synthetic PNG, 2026-07-24)
# Script: scripts/eval_nvidia_models.py

| Model | ok | proposals | dates (raw) | notes |
|-------|----|-----------|-------------|-------|
| nvidia/nemotron-nano-12b-v2-vl | yes | 6 | 2 dates | **chosen default** — best coverage |
| nvidia/llama-3.1-nemotron-nano-vl-8b-v1 | yes | 6 | 2 dates | similar; slightly heavier |
| meta/llama-3.2-11b-vision-instruct | yes | 1 | 1 date | weaker on this sample |

Date caveat: models initially mis-parsed EU D.M.YYYY as month-first; prompt now forces day-first Czech dates. Classic `parse_multi_date_table` remains authoritative for text tables.

Default env: `SMART_MODEL=nvidia/nemotron-nano-12b-v2-vl`
