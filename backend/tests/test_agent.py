"""Offline tests for the agent's guardrails (no LLM, tiny synthetic DB)."""

import pytest

from backend.agent.service import detect_language
from backend.agent.sql import SQLRejected, SQLRunner
from backend.agent.verify import verify_answer


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE main.deals",
        "SELECT 1; SELECT 2",
        "INSERT INTO t VALUES (1)",
        "CREATE TABLE x AS SELECT 1",
        "SELECT * FROM read_csv('/etc/passwd')",
        "ATTACH 'other.db'",
        "COPY (SELECT 1) TO 'out.csv'",
        "PRAGMA database_list",
        "",
    ],
)
def test_guard_rejects_non_select(sql):
    with pytest.raises(SQLRejected):
        SQLRunner.check(sql)


def test_guard_accepts_select_and_cte():
    assert SQLRunner.check("WITH a AS (SELECT 1 x) SELECT x FROM a;").startswith("WITH")


RESULTS = [
    {
        "rows": [[2024, 106647, "45900904000492.5", 12.35, "Бензин АИ-92"]],
        "row_count": 1,
    }
]


def test_verify_accepts_formatted_and_scaled_numbers():
    answer = (
        "В 2024 году **106 647** сделок на 45 900 904 000 492,50 сум "
        "(≈45,9 трлн сум), рост 12,35 %. Товар АИ-92."
    )
    report = verify_answer(answer, RESULTS)
    assert report.ok and report.checked >= 4


def test_verify_flags_invented_numbers():
    report = verify_answer("Сделок: 106 650", RESULTS)
    assert not report.ok and report.unverified == ["106 650"]


def test_verify_ignores_dates_years_and_question_numbers():
    report = verify_answer(
        "_Период: 2022-01-03 – 2026-10-30, топ-10_", RESULTS, "топ-10"
    )
    assert report.ok and report.checked == 0


@pytest.mark.parametrize(
    "text,lang",
    [
        ("Сколько сделок было в 2024 году?", "ru"),
        ("2024-yilda nechta bitim tuzilgan?", "uz"),
        ("Qaysi viloyatda eng ko'p bitim?", "uz"),
        ("2024 йилда нечта битим тузилган?", "uz_cyrl"),
        ("Буғдой бўйича савдо", "uz_cyrl"),
    ],
)
def test_language_detection(text, lang):
    assert detect_language(text) == lang
