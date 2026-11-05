"""Version 1 logical vocabulary; no physical dataset mappings."""

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType


class Metric(StrEnum):
    DEAL_COUNT = "deal_count"
    DEAL_VALUE = "deal_value"
    PHYSICAL_VOLUME = "physical_volume"
    DELIVERED_LOTS = "delivered_lots"
    AVERAGE_UNIT_PRICE = "average_unit_price"


class Dimension(StrEnum):
    DEAL_DATE = "deal_date"
    DEAL_YEAR = "deal_year"
    WAREHOUSE_REGION = "warehouse_region"
    SELLER_INN = "seller_inn"
    BUYER_INN = "buyer_inn"
    SELLER_BROKER_CODE = "seller_broker_code"
    BUYER_BROKER_CODE = "buyer_broker_code"
    PRODUCT = "product"
    PRODUCT_ID = "product_id"
    CONTRACT_TYPE = "contract_type"
    CONTRACT_FORM = "contract_form"
    STATUS = "status"
    CURRENCY = "currency"
    MEASUREMENT_UNIT = "measurement_unit"
    DELIVERY_COMPLETION = "delivery_completion"


class Currency(StrEnum):
    UZS = "UZS"
    USD = "USD"


class Unit(StrEnum):
    KG = "kg"
    TONNE = "tonne"
    LITRE = "litre"
    CUBIC_METRE = "cubic_metre"
    PIECE = "piece"


@dataclass(frozen=True)
class MetricDefinition:
    definition: str
    required_fields: tuple[str, ...]
    monetary: bool = False
    physical: bool = False


METRICS = MappingProxyType(
    {
        Metric.DEAL_COUNT: MetricDefinition(
            "Count transactions at one row per deal; never count joined duplicates.",
            ("deal_id",),
        ),
        Metric.DEAL_VALUE: MetricDefinition(
            "Sum executed transaction amounts under the currency policy.",
            ("transaction_amount", "currency"),
            monetary=True,
        ),
        Metric.PHYSICAL_VOLUME: MetricDefinition(
            "Sum deal_quantity_lots * lot_size within compatible units.",
            ("deal_quantity_lots", "lot_size", "measurement_unit"),
            physical=True,
        ),
        Metric.DELIVERED_LOTS: MetricDefinition(
            "Sum delivered lots; not transaction count or delivered physical volume.",
            ("delivered_lots",),
        ),
        Metric.AVERAGE_UNIT_PRICE: MetricDefinition(
            "Sum executed amounts / sum physical volume; "
            "volume-weighted, not starting price.",
            (
                "transaction_amount",
                "currency",
                "deal_quantity_lots",
                "lot_size",
                "measurement_unit",
                "product",
            ),
            monetary=True,
            physical=True,
        ),
    }
)


class NumericField(StrEnum):
    DEAL_QUANTITY_LOTS = "deal_quantity_lots"
    DELIVERED_LOTS = "delivered_lots"
    TRANSACTION_AMOUNT = "transaction_amount"
    PHYSICAL_VOLUME = "physical_volume"
    EXECUTED_UNIT_PRICE = "executed_unit_price"


class LookupField(StrEnum):
    DEAL_ID = "deal_id"
    DEAL_DATE = "deal_date"
    WAREHOUSE_REGION = "warehouse_region"
    SELLER_INN = "seller_inn"
    BUYER_INN = "buyer_inn"
    SELLER_BROKER_CODE = "seller_broker_code"
    BUYER_BROKER_CODE = "buyer_broker_code"
    PRODUCT = "product"
    PRODUCT_ID = "product_id"
    CONTRACT_TYPE = "contract_type"
    CONTRACT_FORM = "contract_form"
    STATUS = "status"
    DELIVERY_COMPLETION = "delivery_completion"
    CURRENCY = "currency"
    MEASUREMENT_UNIT = "measurement_unit"
    DEAL_QUANTITY_LOTS = "deal_quantity_lots"
    DELIVERED_LOTS = "delivered_lots"
    LOT_SIZE = "lot_size"
    TRANSACTION_AMOUNT = "transaction_amount"
    PHYSICAL_VOLUME = "physical_volume"
    EXECUTED_UNIT_PRICE = "executed_unit_price"


# Exact factors only. Source-label mappings must still be verified at execution.
MASS_UNITS = frozenset({Unit.KG, Unit.TONNE})
MONETARY_FIELDS = frozenset(
    {
        NumericField.TRANSACTION_AMOUNT,
        NumericField.EXECUTED_UNIT_PRICE,
    }
)
PHYSICAL_FIELDS = frozenset(
    {
        NumericField.PHYSICAL_VOLUME,
        NumericField.EXECUTED_UNIT_PRICE,
    }
)
