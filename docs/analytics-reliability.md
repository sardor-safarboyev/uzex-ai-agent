# Analytical reliability diagnosis

Branch: `fix/analytics-reliability-verified`. The starting working tree was clean,
with no merge in progress. No commits, pushes, merges, deployment, ingestion or
dataset edits were performed.

## Evidence and limits

No local API/Vite process or saved backend log was present. Neither GROQ_API_KEY
nor UZEX_DATABASE_PATH was set in the process environment. The ignored existing
`.env` supplied a key when explicitly loaded. Two live calls were made, without
retries: C answered correctly with all five yearly counts; E returned HTTP 503
with `rate_limit` after Groq HTTP 429. No further live calls were made.
Historical responses were not supplied, so their exact causes remain unknown.
Mocked responses test the actual interpreter, API, validated plans, deterministic
compiler and immutable 500,000-deal DuckDB file.

The observed rate limit motivated a small deterministic route for anchored
supported question templates. A–G and the explicit count-ranking/currency variants
now produce validated logical plans without a provider call or key. Full-string
matching rejects additional clauses instead of dropping constraints. Other wording
still uses Groq and remains subject to quota/provider errors. There is no result
cache or hardcoded analytical answer: all numeric answers execute read-only SQL.

Baseline: 77 existing interpretation/API/real-data integration tests passed.
`deal_year` reproducibly failed schema validation before the extension. Existing
top-N, warehouse-region, source-money and comparison execution paths passed;
there was no evidence warranting a rewrite of their SQL.

## Priority questions

| Case | Diagnosed contract behavior / gap | Verified outcome |
| --- | --- | --- |
| A: 2024 total value | Currency omitted; summing currencies would be invalid. Prompt lacked a year-specific money example. | Currency clarification. Explicit UZS total: 43279503660342.3100000000 UZS; explicit USD total: 219306395.3500000000 USD (independent read-only SQL). |
| B: most sold 5 products in 2025 | Measure ambiguous (deal count versus physical volume); existing ranking requires an explicit metric. Normalized product IDs remain unsupported. | Measure clarification. Explicit top 5 by deal count is verified below. |
| C: deal counts by year | No year grouping dimension existed in schema/compiler; a year grouping plan became invalid_response. | Added allowlisted deal_year; verified all five counts. |
| D: leading region in 2023 | Existing warehouse-region ranking works; generic region wording needed explicit prompt guidance. No verified seller/buyer geography. | Warehouse region Toshkent shahri: 14856 deals. |
| E: compare 2024/2025 counts | Existing comparison executor works; prompt lacked a concrete comparison plan. | 106647 versus 115763; target minus baseline = 9116. |
| F: total count | Existing supported path; no reproduced execution defect. | 500000. |
| G: 2024 count | Existing inclusive year date range works; no reproduced execution defect. | 106647. |

For A/B/D/E, exact historical model outputs remain unknown. Added examples guide
valid plans outside templates; mock tests do not establish live interpretation
accuracy for arbitrary phrasing. Live E confirmed rate limiting, not a compiler
defect; its deterministic template now bypasses that failure.
Original A and B deliberately return clarification, not invented numeric answers.

Verified counts: 2022=84299, 2023=93985, 2024=106647, 2025=115763, 2026=99306.

Explicit 2025 product ranking by deal count, retaining source names:

| Product | Deals |
| --- | ---: |
| Сахар белый | 3039 |
| Пшеница продовольственная Класс 4 класс | 2470 |
| Дизельное топливо Марка ДТ-Е-К5 | 2241 |
| Аммиачная селитра Марка Б | 2024 |
| ПОРТЛАНДЦЕМЕНТ Марка ЦЕМ II/В-К 32,5Н | 1786 |

API statuses retain existing compatibility: `unsupported` means unsupported_query,
`ambiguous` means clarification_needed. Errors preserve `provider_error`,
`rate_limit`, `invalid_response`, `execution_failed`, `internal_error` and other
existing codes. API errors now have concise localized messages. Safe logs record
only stage and code; invalid JSON and plan validation have distinct log stages.
Frontend parsing already retained structured error bodies on HTTP 503; no parsing
defect was reproduced. Added localized year/measure labels and clearer invalid
plan explanations. Bilingual synthetic-data disclaimers remain intact.

## Manual checks

Offline priority API test (mock provider, real read-only database):

```sh
cd backend
uv run pytest tests/test_analytics_reliability.py -v
uv run pytest
uv run ruff check .
```

Frontend checks:

```sh
cd frontend
npm test
npm run build
```

Start a local API with your existing Groq key exported securely in the shell:

```sh
cd backend
UZEX_DATABASE_PATH="$PWD/../data/processed/uzex.duckdb" uv run --env-file ../.env uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

The exact templates below execute without Groq; other wording may consume quota:

```sh
curl -sS http://127.0.0.1:8000/health
curl -sS http://127.0.0.1:8000/api/ask -H 'Content-Type: application/json' -d '{"question":"Покажи количество сделок по годам."}'
curl -sS http://127.0.0.1:8000/api/ask -H 'Content-Type: application/json' -d '{"question":"2025-yilda bitimlar soni bo‘yicha top 5 mahsulot"}'
curl -sS http://127.0.0.1:8000/api/ask -H 'Content-Type: application/json' -d '{"question":"Сравни количество сделок за 2024 и 2025 годы."}'
```

Deployment blockers: Groq rate limiting is observed for questions outside the
anchored templates; general live interpretation remains only partially verified.
Load the existing `.env` explicitly or export its key securely for Groq questions.
The database path must point to the supplied offline-built snapshot.
USD conversion, normalized product IDs and seller/buyer
geography remain unsupported until their semantics/mappings are verified.
Docker configuration was unchanged.

## Files changed

- `backend/src/backend/interpretation/templates.py`: anchored question-to-plan route.
- `backend/src/backend/interpretation/service.py`: routing, logical examples, safe failure stages.
- `backend/src/backend/semantic/registry.py`: calendar-year dimension.
- `backend/src/backend/semantic/models.py`: version/filter validation for that dimension.
- `backend/src/backend/query/mappings.py`: fixed year expression.
- `backend/src/backend/api/ask.py`: localized errors/clarifications and safe stage logging.
- `backend/tests/test_analytics_reliability.py`: mocked provider, no-provider templates and real read-only reconciliation.
- `backend/tests/test_query_plan.py`: validates the additional documented JSON example.
- `frontend/src/presentation.js`: bilingual year/measure and invalid-plan explanations.
- `frontend/src/presentation.test.js`: presentation regressions.
- `docs/query-plan.md`, `docs/semantic-contract.md`, this report: contract and evidence.

No dependencies were changed. `backend/uv.lock` remains consistent and unchanged.

## Final validation

- `cd backend && uv run pytest`: **395 passed**, 1 existing Starlette/httpx
  deprecation warning, 44.31 seconds. Includes 18 analytical reliability tests.
- `cd backend && uv run ruff check .`: **all checks passed**.
- `cd backend && uv lock --check`: **passed**, 28 packages resolved, no changes.
- `cd frontend && npm test`: **15 passed**, 0 failed/skipped; includes Chrome at
  mobile narrow, mobile and laptop sizes.
- `cd frontend && npm run build`: **passed**, Vite production bundle generated.
- `git diff --check`: **passed**.
- Real-data reconciliation verified all five yearly counts, 500000 total,
  product/warehouse-region ranking, separate-currency monetary values and
  deterministic comparison. Existing integration checks confirmed snapshot and
  source hashes unchanged. Reference queries use separate read-only connections.
- Live Groq: **1 answered, 1 rate-limited**, exactly 2 calls, no retries. The
  comparison now succeeds through its deterministic template without Groq.

The initial frontend sandbox run could not run the Chrome test; rerunning with
the required process permissions passed all frontend tests. No runtime dependency
or browser installation was needed.
