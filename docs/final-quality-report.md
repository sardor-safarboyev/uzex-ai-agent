# Final analytics quality report

## Git safety

Started on clean `main` at `ff55ca0`, after the previous analytics fix was merged.
No merge was in progress and `fix/final-quality` did not exist. Created that
branch. All changes remain uncommitted. No reset, discard, push, merge, PR or
deployment was performed. No dependencies, credentials, CSVs or database were
changed. `uv.lock` remains consistent and unchanged.

## Confirmed causes of the reported failures

1. **UZS comparison:** the template did not recognize the combined Uzbek wording.
   More fundamentally, `AggregateRequest` required a money policy exactly for
   monetary metrics/predicates, so `deal_count` with an explicit UZS source policy
   was rejected. Currency text filters were also forbidden. Thus the existing SQL
   population selector had no valid count-plan representation. The parser mapped
   schema validation failure to `invalid_response`. A mocked valid-JSON response
   with an invalid currency filter reproduces that API failure. The original live
   Groq payload was not supplied, so its exact invalid shape cannot be asserted.
   Version 1.1 now permits only an explicit source-currency policy for nonmonetary
   queries, including comparisons. Conversion and unspecified-currency policies
   remain invalid there. The exact reported wording has an anchored offline
   template; extra clauses are not silently dropped.
2. **2028 clarification:** the count template did not accept `UZEX orqali`, and
   there was no API availability check before Groq. Provider clarification was
   consequently accepted without checking whether the clearly requested year
   existed. Explicit year requests now use distinct actual deal years read from
   a verified immutable snapshot. Absent years return `insufficient_data` with
   reason `outside_coverage`, structured availability metadata and a localized
   explanation. No zero is inferred. Tests cover 2021, 2027, 2028 and all valid
   years, Russian, Uzbek and explicit language override.

The UI rendered the same error in both the answer heading and a separate error
box, which also appended the internal code. It now renders one localized alert.
Invalid provider output is described as a service failure, not user ambiguity.

## Verified analytics

Independent SQL uses separate read-only DuckDB connections and does not reuse
compiler expressions to obtain expected aggregates.

| Capability | Verified result |
| --- | --- |
| UZS counts, 2024 versus 2025 | 105320 versus 114396; 2025 leads by 9076 |
| All-currency counts, 2024 versus 2025 | 106647 versus 115763; difference 9116 |
| Year grouping | 2022=84299, 2023=93985, 2024=106647, 2025=115763, 2026=99306 |
| Total / sum of years | 500000 |
| 2023 leading warehouse region | Toshkent shahri, 14856 deals |
| Product TOP 5 / TOP 10, 2025 | Exact source-name ranking reconciles against independent SQL |
| UZS 2024 transaction amount | 43279503660342.3100000000 UZS |
| USD 2024 transaction amount | 219306395.3500000000 USD |
| Combined year + currency + region | Exact source region and currency predicates reconcile independently |

Uzbek and Russian templates support source-currency comparisons and product
rankings. For an explicit combined filter, use:

`2024-yilda UZS valyutasidagi bitimlar soni, ombor hududi: Toshkent shahri`

Region values remain exact source text. A SQL-looking region is bound as a
literal value and returns no matches; it cannot change predicates. Unrecognized
wording retains the Groq path and strict validation. A recognized question is
never answered from hardcoded counts or cached model claims.

## Missing information and unsupported operations

Inspected the actual `main` schema and existing semantic/physical contracts.
There are no net-profit/expense amounts, employee counts or paid-tax amounts.
`vat_payer_source` is a status, not evidence of tax payment. The supplied example
questions now have specific `insufficient_data` explanations. Known unsupported
operations have typed explanations for median, forecasting and causal claims.
“Most sold” without a measure still asks deal count versus physical volume.

USD-to-UZS conversion remains unsupported because execution timezone/rounding
semantics are unverified. Normalized product IDs and seller/buyer geography are
not introduced. No LLM SQL, arbitrary expressions, guessed joins or new
analytical operations were added.

## Errors and UI

- Missing coverage: `insufficient_data` / `outside_coverage`.
- Missing source fields: `insufficient_data` with a specific unavailable-field reason.
- Genuine ambiguity: `ambiguous` with a specific currency/unit/measure question.
- Unsupported calculation: `unsupported` with a typed limitation.
- Invalid provider JSON/plan: `error` / `invalid_response`; never a claimed answer.
- Groq 429: `error` / `rate_limit`, localized retry message.
- Unexpected application error: `error` / `internal_error`.
- Valid empty match within available years: `no_match`.
- Invalid request: HTTP 422, `error` / `invalid_input`, no echoed input or SQL.

API codes remain available for diagnostics. Server logs retain safe stage/code
messages without provider bodies, prompts, credentials or SQL. The normal UI
does not show raw error codes, duplicate errors, empty tables or empty evidence.
Nonanswer cards are compact; meaningful evidence remains collapsible.

Count comparisons, annual groupings and leading warehouse regions have
deterministic summaries derived from validated result data. Source names remain
unchanged. Annual comparison summaries require complete calendar-year periods;
they do not mislabel a month as a whole-year comparison. Requested TOP N is
intentional selection, not truncation. A server cap below requested N still
produces a real truncation warning. Coverage population counts remain intact.
The bilingual UI, synthetic-data disclaimer, typography, colors and layout remain.

## Exact validation results

- `cd backend && uv run pytest`: **422 passed**, one existing Starlette/httpx
  deprecation warning, **54.62 seconds**. Includes 27 new final-quality tests.
- `cd backend && uv run ruff check .`: **passed**.
- `cd backend && uv lock --check`: **passed**, 28 packages, lock unchanged.
- `cd frontend && npm test`: **17 passed**, zero failures/skips. Includes Chrome
  regressions at narrow-mobile, mobile and laptop sizes, checking one alert,
  hidden internal codes, compact nonanswers, availability localization and TOP 1.
- `cd frontend && npm run build`: **passed**.
- Docker Compose backend and frontend image builds: **passed** on final sources.
- Isolated local Compose smoke: both containers **healthy**, backend `/health`
  and frontend `/` returned HTTP 200, and **six real requests through the frontend
  proxy passed**: UZS comparison, 2028 availability, region leader, ordinary year
  comparison, product TOP 10 and all-year grouping.
- Smoke containers ran with **Groq disabled** and the database bind mounted
  `read_write=false`. No live Groq calls were made during this task.
- Temporary containers/network were removed after the smoke test. No production
  ports, deployments or existing containers were changed.
- Database and all source hashes matched their original manifests after tests
  and after Docker smoke tests.
- `git diff --check`: **passed**.

The Docker smoke used a temporary override in `/tmp` on ports 18080/18081 and
project `uzex-final-quality`, leaving repository Docker configuration unchanged.

## Exact repository files changed

1. `backend/src/backend/api/ask.py`
2. `backend/src/backend/api/availability.py` (new)
3. `backend/src/backend/api/summaries.py` (new)
4. `backend/src/backend/interpretation/service.py`
5. `backend/src/backend/interpretation/templates.py`
6. `backend/src/backend/main.py`
7. `backend/src/backend/query/engine.py`
8. `backend/src/backend/semantic/models.py`
9. `backend/tests/test_final_quality.py` (new)
10. `backend/tests/test_query_execution.py`
11. `backend/tests/test_query_plan.py`
12. `frontend/src/main.jsx`
13. `frontend/src/presentation.js`
14. `frontend/src/presentation.test.js`
15. `frontend/src/style.css`
16. `frontend/tests/browser.test.js`
17. `frontend/tests/presentation.test.js`
18. `docs/query-plan.md`
19. `docs/semantic-contract.md`
20. `docs/final-quality-report.md` (this report, new)

## Five manual browser questions

1. `2024 va 2025-yillarda UZS valyutasidagi bitimlar sonini alohida ko‘rsat va qaysi yilda ko‘proq bo‘lganini aniqlang.`
   Expect 105320 / 114396, 2025 leads, difference 9076, currency UZS.
2. `2025-yilda bitimlar soni bo‘yicha top 10 mahsulot`
   Expect ten products, stable count ordering, no misleading truncation warning.
3. `Покажи количество сделок по годам.`
   Expect five yearly counts summing to 500000 and a Russian summary.
4. `2023-yilda qaysi hududda eng ko‘p bitim tuzilgan?`
   Expect warehouse region Toshkent shahri / 14856; no TOP 1 warning.
5. `2028-yilda UZEX orqali nechta bitim tuzilgan?`
   Expect a missing-data explanation for 2028 with verified 2022–2026 coverage,
   no zero count, no clarification, no raw code. Toggle Russian to check translation.

Recommended commit, after reviewing the diff (not executed):

```sh
git add backend/src backend/tests frontend/src frontend/tests docs
git commit -m "fix: finalize analytics reliability and error presentation"
```

## Deployment readiness

Ready for the verified hackathon flows: full tests, production frontend build,
both container builds and real container/proxy analytics passed. Mount the same
offline-built snapshot read-only. Other natural-language phrasing still depends
on Groq availability/quota and validated interpretation; this task intentionally
did not consume live quota to assess arbitrary paraphrases. Availability checks
verify the snapshot before reading years, which adds a bounded read-only check
to explicit-year API requests. No known new security blocker remains.
