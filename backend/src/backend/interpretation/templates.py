"""Anchored analytical templates; no fuzzy entities, SQL or inferred answers."""

import re

from backend.semantic.models import QueryPlan


def yearly_count_claim(question: str) -> tuple[int, int] | None:
    text = " ".join(question.lower().strip().rstrip("?.").split())
    match = re.fullmatch(
        r"((?:19|20)\d{2})-yilda "
        r"([0-9]{1,12}|[0-9]{1,3}(?: [0-9]{3}){1,3}) "
        r"ta bitim tuzilgan\. tasdiqla",
        text,
    )
    return (int(match[1]), int(match[2].replace(" ", ""))) if match else None


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

    if claim := yearly_count_claim(question):
        # The asserted count is deliberately absent from the executable plan.
        return QueryPlan.model_validate(
            {
                "version": "1.1",
                "language": language,
                "request": aggregate(date_range=period(claim[0])),
            }
        )

    yearly = re.fullmatch(
        r"((?:19|20)\d{2})\s*[-–—]\s*((?:19|20)\d{2})-yillarda "
        r"bitimlar sonining yillik o'sish yoki kamayish foizlarini hisobla",
        text,
    )
    if yearly:
        first, last = map(int, yearly.groups())
        if last == first + 1:
            request = {
                "kind": "comparison",
                "baseline": period(first),
                "target": period(last),
                "aggregate": aggregate(),
                "changes": ["percentage_change"],
            }
        else:
            request = {
                "kind": "unsupported",
                "reason": "unsupported_yearly_series",
                "explanation": (
                    "Only a single two-period percentage comparison is supported."
                ),
            }
        return QueryPlan.model_validate(
            {"version": "1.1", "language": language, "request": request}
        )

    limitations = [
        (
            r"(?:19|20)\d{2}-yilda kompaniyalarning sof foydasi qancha",
            "unavailable_profit",
        ),
        (
            r"(?:19|20)\d{2}-yilda kompaniyalarda nechta xodim ishlagan",
            "unavailable_employees",
        ),
        (
            r"(?:19|20)\d{2}-yilda qaysi broker eng ko'p soliq to'lagan",
            "unavailable_tax",
        ),
        (
            r"(?:19|20)\d{2}-yilda eng ko'p sotilgan mahsulot "
            r"nima sababdan yetakchi bo'lgan",
            "unsupported_causality",
        ),
        (
            r"(?:19|20)\d{2}-yilda barcha usd bitimlarini uzs ga aylantir",
            "currency_conversion",
        ),
    ]
    reason = next(
        (reason for pattern, reason in limitations if re.fullmatch(pattern, text)), None
    )
    if reason is None and re.search(r"\b(?:median\w*|медиан\w*)\b", text):
        reason = "unsupported_statistic"
    if reason is None and re.search(r"\b(?:bashorat\w*|prognoz\w*|прогноз\w*)\b", text):
        reason = "unsupported_forecast"
    if reason is None and re.search(
        r"\b(?:rentabellik\w*|profitability|рентабельност\w*)\b", text
    ):
        reason = "unavailable_profit"
    if reason:
        request = {
            "kind": "unsupported",
            "reason": reason,
            "explanation": "Requested information or operation is not verified.",
        }
    elif match := re.fullmatch(
        r"сравни количество сделок в (uzs|usd) за ((?:19|20)\d{2}) и "
        r"((?:19|20)\d{2}) годы",
        text,
    ):
        first, second = sorted([match[2], match[3]])
        if first == second:
            return None
        request = {
            "kind": "comparison",
            "baseline": period(first),
            "target": period(second),
            "aggregate": aggregate(
                money={"mode": "source", "source_currency": match[1].upper()}
            ),
            "changes": ["absolute_difference"],
        }
    elif match := re.fullmatch(
        r"топ (5|10) товаров по количеству сделок за ((?:19|20)\d{2}) год", text
    ):
        request = aggregate(
            group_by=["product"],
            date_range=period(match[2]),
            ranking={
                "metric": "deal_count",
                "direction": "top",
                "count": int(match[1]),
            },
        )
    elif match := re.fullmatch(r"сколько сделок за ((?:19|20)\d{2}) год", text):
        request = aggregate(date_range=period(match[1]))
    elif match := re.fullmatch(
        r"общая сумма сделок в (uzs|usd) за ((?:19|20)\d{2}) год", text
    ):
        request = aggregate(
            metrics=["deal_value"],
            date_range=period(match[2]),
            money={"mode": "source", "source_currency": match[1].upper()},
        )
    elif match := re.fullmatch(
        r"((?:19|20)\d{2})-yilda (uzs|usd) valyutasidagi bitimlar soni qancha", text
    ):
        request = aggregate(
            date_range=period(match[1]),
            money={"mode": "source", "source_currency": match[2].upper()},
        )
    elif text == "сколько всего сделок":
        request = aggregate()
    elif text in {"покажи количество сделок по годам", "yillar bo'yicha bitimlar soni"}:
        request = aggregate(group_by=["deal_year"])
    elif match := re.fullmatch(
        r"((?:19|20)\d{2})-yilda (?:uzex orqali )?nechta bitim tuzilgan", text
    ):
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
        r"((?:19|20)\d{2})-yilda bitimlar soni bo'yicha top (5|10) mahsulot", text
    ):
        request = aggregate(
            group_by=["product"],
            date_range=period(match[1]),
            ranking={
                "metric": "deal_count",
                "direction": "top",
                "count": int(match[2]),
            },
        )
    elif match := re.fullmatch(
        r"((?:19|20)\d{2}) va ((?:19|20)\d{2})-yillarda (uzs|usd) valyutasidagi "
        r"bitimlar sonini alohida ko'rsat va qaysi yilda ko'proq bo'lganini aniqlang",
        text,
    ):
        first, second = sorted([match[1], match[2]])
        if first == second:
            return None
        request = {
            "kind": "comparison",
            "baseline": period(first),
            "target": period(second),
            "aggregate": aggregate(
                money={"mode": "source", "source_currency": match[3].upper()}
            ),
            "changes": ["absolute_difference"],
        }
    elif text in {
        "viloyatlar bo'yicha bitimlar soni qancha",
        "сколько сделок по каждому региону склада",
    }:
        request = aggregate(group_by=["warehouse_region"])
    elif match := re.fullmatch(
        r"((?:19|20)\d{2})-yilda (uzs|usd) valyutasidagi bitimlar soni, "
        r"ombor hududi: (.+)",
        " ".join(question.strip().rstrip("?.").split()),
        flags=re.IGNORECASE,
    ):
        request = aggregate(
            date_range=period(match[1]),
            money={"mode": "source", "source_currency": match[2].upper()},
            filters=[
                {"field": "warehouse_region", "operator": "eq", "values": [match[3]]}
            ],
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
