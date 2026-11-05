"""Deterministic deal-count summaries from validated scope and actual rows."""

from backend.query.models import QueryExecution


def count_summary(execution: QueryExecution) -> str | None:
    if execution.result.outcome.status != "answered" or not execution.scope:
        return None
    request = execution.scope.request
    language = execution.result.language
    table = execution.result.outcome.data
    fields = [column.field for column in table.columns]

    def number(value):
        return f"{int(value):,}".replace(",", " ")

    if request.kind == "comparison" and request.aggregate.metrics == ["deal_count"]:
        values = dict(zip(fields, table.rows[0], strict=True))
        a, b = request.baseline.start.year, request.target.start.year
        if any(
            period.start.year != period.end.year
            or (period.start.month, period.start.day) != (1, 1)
            or (period.end.month, period.end.day) != (12, 31)
            for period in (request.baseline, request.target)
        ):
            return None
        currency = (
            request.aggregate.money.source_currency if request.aggregate.money else None
        )
        suffix = f" ({currency})" if currency else ""
        first, second = number(values["baseline"]), number(values["target"])
        winner = a if values["baseline"] > values["target"] else b
        if language == "uz":
            text = (
                f"{a}-yilda {first} ta, {b}-yilda {second} ta "
                f"bitim qayd etilgan{suffix}."
            )
            text += (
                f" Ko‘proq bitim: {winner}-yilda."
                if values["baseline"] != values["target"]
                else " Bitimlar soni teng."
            )
        else:
            text = f"В {a} году — {first}, в {b} году — {second} сделок{suffix}."
            text += (
                f" Больше сделок в {winner} году."
                if values["baseline"] != values["target"]
                else " Количество сделок одинаково."
            )
        if "absolute_difference" in values:
            difference = number(abs(values["absolute_difference"]))
            text += (
                f" Farq: {difference} ta."
                if language == "uz"
                else f" Разница: {difference}."
            )
        return text
    if request.kind != "aggregate" or request.metrics != ["deal_count"]:
        return None
    if (
        fields == ["warehouse_region", "deal_count"]
        and request.ranking
        and request.ranking.count == 1
        and request.ranking.direction == "top"
    ):
        name, count = table.rows[0]
        if name is None:
            return None
        year = (
            request.date_range.start.year
            if request.date_range
            and request.date_range.start.year == request.date_range.end.year
            else None
        )
        if language == "uz":
            return (
                f"{str(year) + '-yilda ' if year else ''}"
                f"Ombor hududlari bo‘yicha yetakchi: {name} — "
                f"{number(count)} ta bitim."
            )
        return (
            f"{'В ' + str(year) + ' году ' if year else ''}"
            f"Лидер по региону склада: {name} — {number(count)} сделок."
        )
    if fields == ["deal_year", "deal_count"]:
        values = "; ".join(f"{year}: {number(count)}" for year, count in table.rows)
        return (
            (
                "Yillar bo‘yicha bitimlar soni: "
                if language == "uz"
                else "Количество сделок по годам: "
            )
            + values
            + "."
        )
    if fields == ["product", "deal_count"] and request.ranking:
        return (
            f"Bitimlar soni bo‘yicha {len(table.rows)} ta mahsulot "
            "jadvalda ko‘rsatilgan."
            if language == "uz"
            else f"В таблице {len(table.rows)} товаров по количеству сделок."
        )
    return None
