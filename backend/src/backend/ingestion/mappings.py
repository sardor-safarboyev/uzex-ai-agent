"""Explicit ingestion mappings derived from inspected headers; no fuzzy resolution."""

from dataclasses import dataclass

from backend.profiling.statistics import identifier


@dataclass(frozen=True)
class Field:
    source: str
    target: str
    kind: str = "text"

    @property
    def sql_type(self) -> str:
        return {
            "text": "VARCHAR",
            "date": "DATE",
            "time": "TIME",
            "decimal": "DECIMAL(38,10)",
        }[self.kind]

    def expression(self, alias: str = "r") -> str:
        value = f"{alias}.{identifier(self.source)}"
        if self.kind == "text":
            return f"nullif({value}, '')"
        if self.kind in {"date", "time"}:
            pattern = (
                "[0-9]{2}\\.[0-9]{2}\\.[0-9]{4}"
                if self.kind == "date"
                else "[0-9]{2}:[0-9]{2}:[0-9]{2}"
            )
            fmt = "%d.%m.%Y" if self.kind == "date" else "%H:%M:%S"
            return (
                f"CASE WHEN regexp_full_match({value}, '{pattern}') "
                f"THEN try_strptime({value}, '{fmt}')::{self.sql_type} END"
            )
        # Only the observed dot decimal / ASCII-space grouping convention is
        # approved for ingestion. No diagnostic decimal-comma interpretation.
        pattern = r"[+-]?(?:[0-9]+|[0-9]{1,3}(?: [0-9]{3})+)(?:\.[0-9]{1,10})?"
        return (
            f"CASE WHEN regexp_full_match({value}, '{pattern}') "
            f"THEN try_cast(replace({value}, ' ', '') AS DECIMAL(38,10)) END"
        )


DEAL_FIELDS = (
    Field("Номер сделки", "deal_id"),
    Field("Дата сделки", "deal_date", "date"),
    Field("Время сделки", "deal_time", "time"),
    Field("Тип торгов", "auction_type"),
    Field("Количество", "deal_quantity_lots", "decimal"),
    Field("Сумма сделки", "transaction_amount", "decimal"),
    Field("Стартовая цена", "starting_price", "decimal"),
    Field("Номер контракта", "contract_id"),
    Field("Наименование товара", "product_name"),
    Field("Лот", "lot_size", "decimal"),
    Field("Единица измерения", "measurement_unit_source"),
    Field("Регион", "warehouse_region_source"),
    Field("Тип контракта", "contract_type"),
    Field("Форма контракта", "contract_form"),
    Field("Состояние сделки", "official_status"),
    Field("ИНН продавца", "seller_inn"),
    Field("ИНН покупателя", "buyer_inn"),
    Field("Брокер продавца", "seller_broker_code"),
    Field("Брокер покупателя", "buyer_broker_code"),
    Field("Дата оплаты", "payment_date", "date"),
    Field("Дата поставки", "delivery_date", "date"),
    Field("Поставлено", "delivered_lots", "decimal"),
)
CONTRACT_FIELDS = (
    Field("Номер контракта", "contract_id"),
    Field("Наименование продукта", "product_name"),
    Field("Марка товара", "product_brand"),
    Field("Размер товара", "product_size"),
    Field("Сорт товара", "product_grade"),
    Field("Тип товара", "product_type"),
    Field("Класс товара", "product_class"),
    Field("Код ТН ВЭД", "commodity_code"),
    Field("Группа товара", "product_group"),
    Field("Категория товара", "product_category"),
    Field("Отрасль промышленности", "industry"),
    Field("Единица измерения", "measurement_unit_source"),
    Field("Лот", "lot_size", "decimal"),
    Field("Валюта", "currency_source"),
    Field("Базисная цена", "base_price", "decimal"),
    Field("Сумма залога", "deposit_terms_source"),
    Field("Базис поставки", "delivery_basis"),
    Field("Регион", "warehouse_region_source"),
    Field("Адрес склада", "warehouse_address"),
    Field("Тип торгов", "auction_type"),
    Field("Тип контракта", "contract_type"),
    Field("Форма контракта", "contract_form"),
    Field("Срок оплаты", "payment_term_value", "decimal"),
    Field("Срок поставки", "delivery_term_value", "decimal"),
    Field("Упаковка", "packaging"),
    Field("ИНН продавца", "seller_inn"),
    Field("Дата регистрации", "registration_date", "date"),
    Field("Действует до", "valid_until", "date"),
)
PARTICIPANT_FIELDS = (
    Field("ИНН", "inn"),
    Field("Наименование", "company_name"),
    Field("Регион", "registration_region_source"),
    Field("Вид деятельности", "activity_source"),
    Field("Роль", "role_source"),
    Field("Плательщик НДС", "vat_payer_source"),
)
BROKER_FIELDS = (
    Field("Код брокера", "broker_code"),
    Field("Наименование", "company_name"),
    Field("ИНН", "inn_source"),
    Field("Регион", "registration_region_source"),
)
RATE_FIELDS = (
    Field("Дата", "rate_date", "date"),
    Field("Курс", "usd_uzs_rate", "decimal"),
)
MAPPINGS = {
    "deals": DEAL_FIELDS,
    "contracts": CONTRACT_FIELDS,
    "participants": PARTICIPANT_FIELDS,
    "brokers": BROKER_FIELDS,
    "usd_rates": RATE_FIELDS,
}
KEYS = {
    "deals": "deal_id",
    "contracts": "contract_id",
    "participants": "inn",
    "brokers": "broker_code",
    "usd_rates": "rate_date",
}


def currency(expression: str) -> str:
    return (
        f"CASE {expression} WHEN 'Узбекский сум' THEN 'UZS' "
        "WHEN 'Доллар США' THEN 'USD' END"
    )


def unit(expression: str) -> str:
    # Metre and square metre remain source labels; the semantic allowlist does
    # not yet support them. There is no kg/tonne conversion at ingestion.
    return (
        f"CASE {expression} WHEN 'килограмм' THEN 'kg' WHEN 'тонна' THEN 'tonne' "
        "WHEN 'литр' THEN 'litre' WHEN 'куб.метр' THEN 'cubic_metre' "
        "WHEN 'штука' THEN 'piece' END"
    )


DELIVERY_COMPLETION = """
CASE WHEN deal_quantity_lots > 0 AND delivered_lots >= 0
          AND delivered_lots <= deal_quantity_lots
     THEN CASE WHEN delivered_lots = deal_quantity_lots THEN 'fully_delivered'
               WHEN delivered_lots = 0 THEN 'not_delivered'
               ELSE 'partially_delivered' END END
"""

UNRESOLVED = (
    "USD conversion rounding, precision policy and "
    "transaction timezone are unverified; "
    "no USD amount is converted and fx_rate_used remains NULL.",
    "Metre and square-metre source units are preserved; "
    "their semantic unit identifiers "
    "remain NULL pending contract extension. No unit families are combined.",
    "No normalized product_id or company/region alias mapping is established. "
    "Exact names and all contract attributes remain separate.",
    "Broker INNs are not joined to participants. Registration regions are separate "
    "from warehouse-region labels.",
    "Starting/base prices and contract "
    "payment/delivery-term units retain source meaning; "
    "no executed unit price, term-duration rule or "
    "payment-completion inference is added.",
)
