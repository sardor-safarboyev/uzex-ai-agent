"""Check that every number stated in an answer is backed by SQL results.

The answer writer may format numbers (spaces, comma decimals) and add a
rounded short form with a scale word (млн/mln, млрд/mlrd, трлн/trln). A
number is *verified* if it equals a result value exactly, equals it after
rounding to the precision shown, or — for scaled short forms — is within
the rounding error of the shown precision.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

SCALES = {
    "тыс": 1e3,
    "ming": 1e3,
    "минг": 1e3,
    "k": 1e3,
    "млн": 1e6,
    "mln": 1e6,
    "million": 1e6,
    "миллион": 1e6,
    "млрд": 1e9,
    "mlrd": 1e9,
    "milliard": 1e9,
    "миллиард": 1e9,
    "трлн": 1e12,
    "trln": 1e12,
    "trillion": 1e12,
    "триллион": 1e12,
}

# 1 234 567,89 | 1,234,567.89 | 12.5 | 45,9 | 1234 — plus optional scale word
_NUMBER = re.compile(
    r"(?<![\w.,])(-?\d{1,3}(?:[   ]\d{3})+(?:[.,]\d+)?|-?\d+(?:[.,]\d+)?)"
    r"(\s*%|\s*(?:" + "|".join(sorted(SCALES, key=len, reverse=True)) + r")\.?\b)?",
    re.IGNORECASE,
)


@dataclass
class Verification:
    checked: int = 0
    verified: int = 0
    unverified: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.unverified

    def as_dict(self) -> dict:
        return {
            "checked": self.checked,
            "verified": self.verified,
            "unverified": self.unverified,
            "ok": self.ok,
        }


def _parse(text: str) -> tuple[float, int] | None:
    """Return (value, decimals shown)."""
    raw = re.sub(r"[   ]", "", text)
    if "," in raw and "." in raw:
        raw = raw.replace(",", "")
    elif raw.count(",") == 1 and not re.fullmatch(r"-?\d{1,3},\d{3}", raw):
        raw = raw.replace(",", ".")
    elif raw.count(",") >= 1:
        raw = raw.replace(",", "")
    try:
        value = float(raw)
    except ValueError:
        return None
    decimals = len(raw.split(".")[1]) if "." in raw else 0
    return value, decimals


def collect_values(results: list[dict]) -> list[float]:
    values: list[float] = []

    def add(v):
        if isinstance(v, bool) or v is None:
            return
        if isinstance(v, (int, float)):
            values.append(float(v))
        elif isinstance(v, str):
            if re.fullmatch(r"-?\d+(\.\d+)?", v.strip()):
                values.append(float(v))
            else:  # numbers embedded in names (e.g. 'АИ-92') or dates
                for match in re.findall(r"\d+(?:\.\d+)?", v):
                    values.append(float(match))
        elif isinstance(v, list):
            for item in v:
                add(item)

    for result in results:
        for row in result.get("rows", []):
            for v in row:
                add(v)
        add(result.get("row_count"))
    return values


def verify_answer(answer: str, results: list[dict], question: str = "") -> Verification:
    values = collect_values(results)
    question_numbers = {m.group(1) for m in _NUMBER.finditer(question)}
    report = Verification()
    # ignore numbers inside the final italic "basis" line about dates
    for match in _NUMBER.finditer(answer):
        token, suffix = match.group(1), (match.group(2) or "").strip().lower()
        parsed = _parse(token)
        if parsed is None:
            continue
        value, decimals = parsed
        start = match.start()
        context = answer[max(0, start - 1) : match.end() + 1]
        # dates like 2026-10-30 / 03.01.2022 and years, small ordinals, the user's own numbers
        if re.search(r"\d[-./]\d", context) and not suffix and decimals == 0:
            if re.search(
                r"\d{4}-\d{2}|\d{2}\.\d{2}\.\d{4}",
                answer[max(0, start - 8) : match.end() + 8],
            ):
                continue
        if not suffix and decimals == 0 and (2000 <= value <= 2100 or abs(value) <= 31):
            continue
        if token in question_numbers:
            continue
        report.checked += 1
        if _matches(value, decimals, suffix, values):
            report.verified += 1
        else:
            report.unverified.append(match.group(0).strip())
    return report


def _matches(value: float, decimals: int, suffix: str, values: list[float]) -> bool:
    scale = 1.0
    for word, factor in SCALES.items():
        if suffix.startswith(word):
            scale = factor
            break
    if scale > 1:
        target = value * scale
        tolerance = 0.5 * (10**-decimals) * scale + 1e-9
        return any(abs(abs(v) - abs(target)) <= tolerance for v in values)
    tolerance = 0.5 * (10**-decimals) + 1e-9
    for v in values:
        if abs(abs(v) - abs(value)) <= tolerance:
            return True
        # percentage given as fraction in results
        if suffix == "%" and abs(abs(v) * 100 - abs(value)) <= tolerance:
            return True
    return False
