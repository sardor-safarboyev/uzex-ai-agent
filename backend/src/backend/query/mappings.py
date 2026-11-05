"""Reviewed schema-1.0 identifiers and expressions, never user-supplied SQL."""

from types import MappingProxyType

# These are the only joins the compiler can emit. LEFT joins retain the fact
# grain; verified primary keys and scope coverage are checked before execution.
FROM = """
FROM main.deals d
LEFT JOIN main.contracts c ON d.contract_id = c.contract_id
LEFT JOIN main.participants seller ON d.seller_inn = seller.inn
LEFT JOIN main.participants buyer ON d.buyer_inn = buyer.inn
LEFT JOIN main.brokers sb ON d.seller_broker_code = sb.broker_code
LEFT JOIN main.brokers bb ON d.buyer_broker_code = bb.broker_code
"""
CURRENCY = (
    "CASE c.currency_source WHEN 'Узбекский сум' THEN "
    "'UZS' WHEN 'Доллар США' THEN 'USD' END"
)
UNIT = """
CASE d.measurement_unit_source WHEN 'килограмм' THEN 'kg' WHEN 'тонна' THEN 'tonne'
WHEN 'литр' THEN 'litre' WHEN 'куб.метр' THEN 'cubic_metre' WHEN 'штука' THEN
'piece' END
"""
VOLUME = "(d.deal_quantity_lots * d.lot_size)"
DELIVERY = """
CASE WHEN d.deal_quantity_lots > 0 AND d.delivered_lots >= 0
     AND d.delivered_lots <= d.deal_quantity_lots
THEN CASE WHEN d.delivered_lots = d.deal_quantity_lots THEN 'fully_delivered'
          WHEN d.delivered_lots = 0 THEN 'not_delivered'
          ELSE 'partially_delivered' END END
"""
FIELDS = MappingProxyType(
    {
        "deal_id": "d.deal_id",
        "deal_date": "d.deal_date",
        "deal_year": "year(d.deal_date)",
        "warehouse_region": "d.warehouse_region_source",
        "seller_inn": "d.seller_inn",
        "buyer_inn": "d.buyer_inn",
        "seller_broker_code": "d.seller_broker_code",
        "buyer_broker_code": "d.buyer_broker_code",
        "product": "d.product_name",
        "contract_type": "d.contract_type",
        "contract_form": "d.contract_form",
        "status": "d.official_status",
        "currency": CURRENCY,
        "measurement_unit": UNIT,
        "delivery_completion": DELIVERY,
        "deal_quantity_lots": "d.deal_quantity_lots",
        "delivered_lots": "d.delivered_lots",
        "lot_size": "d.lot_size",
        "transaction_amount": "d.transaction_amount",
        "physical_volume": VOLUME,
    }
)
TEXT_OPERATORS = MappingProxyType(
    {"eq": "=", "ne": "<>", "in": "IN", "not_in": "NOT IN"}
)
NUMERIC_OPERATORS = MappingProxyType(
    {"eq": "=", "ne": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
)
METRIC_SQL = MappingProxyType(
    {
        "deal_count": "count(*)",
        "deal_value": "sum(transaction_amount)",
        "physical_volume": "sum(physical_volume)",
        "delivered_lots": "sum(delivered_lots)",
    }
)
PRIMARY_KEYS = MappingProxyType(
    {
        "deals": "deal_id",
        "contracts": "contract_id",
        "participants": "inn",
        "brokers": "broker_code",
    }
)
REQUIRED_COLUMNS = MappingProxyType(
    {
        "deals": {
            "deal_id",
            "deal_date",
            "warehouse_region_source",
            "seller_inn",
            "buyer_inn",
            "seller_broker_code",
            "buyer_broker_code",
            "product_name",
            "contract_type",
            "contract_form",
            "official_status",
            "deal_quantity_lots",
            "delivered_lots",
            "lot_size",
            "transaction_amount",
            "measurement_unit_source",
            "contract_id",
            "source_file",
            "source_record",
        },
        "contracts": {"contract_id", "currency_source"},
        "participants": {"inn"},
        "brokers": {"broker_code"},
    }
)
SOURCES = frozenset(
    [f"deals_{year}.csv" for year in range(2022, 2027)]
    + [
        "contracts.csv",
        "participants.csv",
        "brokers.csv",
        "usd_rates.csv",
    ]
)


def quoted(field: str) -> str:
    # Called only after allowlist membership checks, never for value parameters.
    return '"' + field + '"'
