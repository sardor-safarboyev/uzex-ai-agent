"""Profiling checks tied to observed CSV headers, not runtime schema mappings."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceSpec:
    identifier: str
    dates: tuple[str, ...] = ()
    decimals: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()
    names: tuple[str, ...] = ()
    identifiers: tuple[str, ...] = ()
    times: tuple[str, ...] = ()


DEALS = SourceSpec(
    identifier="Номер сделки",
    dates=("Дата сделки", "Дата оплаты", "Дата поставки"),
    decimals=("Количество", "Сумма сделки", "Стартовая цена", "Лот", "Поставлено"),
    categories=(
        "Тип торгов",
        "Единица измерения",
        "Регион",
        "Тип контракта",
        "Форма контракта",
        "Состояние сделки",
        "Брокер продавца",
        "Брокер покупателя",
    ),
    names=("Наименование товара",),
    identifiers=(
        "Номер сделки",
        "Номер контракта",
        "ИНН продавца",
        "ИНН покупателя",
        "Брокер продавца",
        "Брокер покупателя",
    ),
    times=("Время сделки",),
)
SPECS = {f"deals_{year}.csv": DEALS for year in range(2022, 2027)}
SPECS.update(
    {
        "contracts.csv": SourceSpec(
            identifier="Номер контракта",
            dates=("Дата регистрации", "Действует до"),
            decimals=("Лот", "Базисная цена", "Срок оплаты", "Срок поставки"),
            categories=(
                "Валюта",
                "Единица измерения",
                "Тип контракта",
                "Форма контракта",
            ),
            names=("Наименование продукта",),
            identifiers=("Номер контракта", "ИНН продавца", "Код ТН ВЭД"),
        ),
        "participants.csv": SourceSpec(
            identifier="ИНН",
            identifiers=("ИНН",),
            names=("Наименование",),
            categories=("Регион", "Вид деятельности", "Роль", "Плательщик НДС"),
        ),
        "brokers.csv": SourceSpec(
            identifier="Код брокера",
            identifiers=("Код брокера", "ИНН"),
            names=("Наименование",),
            categories=("Регион",),
        ),
        "usd_rates.csv": SourceSpec(
            identifier="Дата", dates=("Дата",), decimals=("Курс",)
        ),
    }
)
