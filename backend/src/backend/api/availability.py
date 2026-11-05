"""Availability derived from verified snapshot dates, never an invented zero."""

import re

from backend.semantic.models import ContractModel


class Availability(ContractModel):
    available_years: list[int]
    missing_years: list[int]


def requested_years(question: str) -> set[int]:
    text = question.lower()
    years = set(
        re.findall(
            r"(?<!\d)((?:19|20)\d{2})(?=-yil|-йил|\s+год|\s+йил|-\d{2}-\d{2})", text
        )
    )
    years.update(re.findall(r"\b(?:за|в)\s+((?:19|20)\d{2})(?!\d)", text))
    for first, second in re.findall(
        r"(?<!\d)((?:19|20)\d{2})\s+(?:va|и)\s+((?:19|20)\d{2})(?=-yil|\s+год)",
        text,
    ):
        years.update([first, second])
    return {int(year) for year in years}


def availability_message(value: Availability, language: str) -> str:
    first, last = min(value.available_years), max(value.available_years)
    years = ", ".join(map(str, value.missing_years))
    if language == "ru":
        return (
            f"Доступные данные охватывают {first}–{last} годы. "
            f"Данных о сделках за {years} год нет."
        )
    return (
        f"Mavjud ma’lumotlar {first}–{last}-yillarni qamrab oladi. "
        f"{years}-yil bo‘yicha bitimlar ma’lumoti mavjud emas."
    )
