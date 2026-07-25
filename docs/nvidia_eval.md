# NVIDIA Smart model eval

## 2026-07-25 — real Příbram multi-column photo

Sample: rotated OpenLIMS comparison printout with **3 date columns**
(`14. 10. 2020`, `18. 5. 2016`, `14. 9. 2010`).

| Model | date layout | dates found | extract draws | notes |
|-------|-------------|-------------|---------------|-------|
| nvidia/nemotron-nano-12b-v2-vl | single (wrong) | 1 | 1 | collapses multi-column |
| meta/llama-3.2-90b-vision-instruct | flaky | 2–spam | 2 | misses 2010; date spam risk |
| **nvidia/nemotron-3-nano-omni-30b-a3b-reasoning** | **multi_column** | **3** | **3** | needs JSON-only system prompt (else reasoning dump) |

Default: `SMART_MODEL=nvidia/nemotron-3-nano-omni-30b-a3b-reasoning`

## 2026-07-24 — synthetic PNG (2 dates)

| Model | ok | proposals | dates (raw) | notes |
|-------|----|-----------|-------------|-------|
| nvidia/nemotron-nano-12b-v2-vl | yes | 6 | 2 dates | former default |
| nvidia/llama-3.1-nemotron-nano-vl-8b-v1 | yes | 6 | 2 dates | similar |
| meta/llama-3.2-11b-vision-instruct | yes | 1 | 1 date | weaker |

Classic `parse_multi_date_table` remains authoritative for clean text tables.
