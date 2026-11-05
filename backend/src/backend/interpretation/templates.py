"""Anchored analytical templates; no fuzzy entities, SQL or inferred answers."""

import re

from backend.semantic.models import QueryPlan


def template_plan(question: str) -> QueryPlan | None:
    text = " ".join(question.lower().strip().rstrip("?.").split())
    text = text.translate(str.maketrans({"‘": "'", "’": "'", "ʻ": "'", "`": "'"}))
    request = None
    language = "ru" if re.search("[а-яё]", text) else "uz"

    def aggregate(**fields):
        return {"kind": "aggregate", "metrics": ["deal_count"], **fields}

    def period(year):
        return {"start": f"{year}-01-01", "end": f"{year}-12-31"}

    def clarify(reason, message):
        return {"kind": "clarification", "reason": reason, "question": message}

    if text == "сколько всего сделок":
        request = aggregate()
    elif text in {"покажи количество сделок по годам", "yillar bo'yicha bitimlar soni"}:
        request = aggregate(group_by=["deal_year"])
    elif match := re.fullmatch(r"((?:19|20)\d{2})-yilda nechta bitim tuzilgan", text):
        request = aggregate(date_range=period(match[1]))
    elif match := re.fullmatch(
        r"((?:19|20)\d{2})-yildagi bitimlarning umumiy qiymati qancha", text
    ):
        request = clarify("currency", "Qaysi valyuta kerak: USD yoki UZS?")
    elif match := re.fullmatch(
        r"((?:19|20)\d{2})-yilda (uzs|usd) bitimlarning umumiy qiymati qancha", text
    ):
        request = aggregate(
            metrics=["deal_value"],
            date_range=period(match[1]),
            money={"mode": "source", "source_currency": match[2].upper()},
        )
    elif match := re.fullmatch(
        r"((?:19|20)\d{2})-yilda eng ko'p sotilgan 5 ta mahsulot qaysilar", text
    ):
        request = clarify("ambiguous_metric", "Bitimlar soni yoki jismoniy hajm?")
    elif match := re.fullmatch(
        r"((?:19|20)\d{2})-yilda bitimlar soni bo'yicha top 5 mahsulot", text
    ):
        request = aggregate(
            group_by=["product"],
            date_range=period(match[1]),
            ranking={"metric": "deal_count", "direction": "top", "count": 5},
        )
    elif match := re.fullmatch(
        r"((?:19|20)\d{2})-yilda qaysi hududda eng ko'p bitim tuzilgan", text
    ):
        request = aggregate(
            group_by=["warehouse_region"],
            date_range=period(match[1]),
            ranking={"metric": "deal_count", "direction": "top", "count": 1},
        )
    elif match := re.fullmatch(
        r"сравни количество сделок за ((?:19|20)\d{2}) и ((?:19|20)\d{2}) годы", text
    ):
        first, second = sorted([match[1], match[2]])
        if first == second:
            return None
        request = {
            "kind": "comparison",
            "baseline": period(first),
            "target": period(second),
            "aggregate": aggregate(),
            "changes": ["absolute_difference"],
        }
    if request is None:
        return None
    return QueryPlan.model_validate(
        {"version": "1.1", "language": language, "request": request}
    )
