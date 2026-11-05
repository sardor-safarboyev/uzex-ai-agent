"""Analyst-friendly semantic layer over the validated read-only snapshot.

The physical tables keep source text and DECIMAL(38,10) values, which overflow
in ordinary arithmetic. These temporary views (created per connection, never
persisted) expose clean names, safe numeric types, all joins resolved and the
USD/UZS conversion done once, so generated SQL stays short and correct.
"""

VIEWS_SQL = r"""
CREATE OR REPLACE TEMP VIEW trades AS
SELECT
    d.deal_id::BIGINT                                   AS deal_id,
    d.deal_date,
    year(d.deal_date)::INTEGER                          AS year,
    month(d.deal_date)::INTEGER                         AS month,
    quarter(d.deal_date)::INTEGER                       AS quarter,
    d.deal_time,
    d.auction_type,
    d.contract_type,
    d.contract_form,
    d.official_status                                   AS status,
    d.contract_id::BIGINT                               AS contract_id,
    d.product_name                                      AS product,
    lower(regexp_replace(trim(d.product_name), '[\s\-]+', ' ', 'g')) AS product_norm,
    lower(regexp_replace(trim(c.product_name), '[\s\-]+', ' ', 'g')) AS product_base,
    CASE
        WHEN regexp_matches(lower(regexp_replace(trim(c.product_name), '[\s\-]+', ' ', 'g')), 'хлопок сырец') THEN 'Хлопок-сырец'
        WHEN regexp_matches(lower(regexp_replace(trim(c.product_name), '[\s\-]+', ' ', 'g')), 'масло хлопков|хлопковое масло') THEN 'Масло хлопковое'
        WHEN regexp_matches(lower(regexp_replace(trim(c.product_name), '[\s\-]+', ' ', 'g')), 'шрот') THEN 'Шрот хлопковый'
        WHEN regexp_matches(lower(regexp_replace(trim(c.product_name), '[\s\-]+', ' ', 'g')), 'пряжа') THEN 'Пряжа хлопковая'
        WHEN regexp_matches(lower(regexp_replace(trim(c.product_name), '[\s\-]+', ' ', 'g')), 'цемент') THEN 'Цемент'
        WHEN regexp_matches(lower(regexp_replace(trim(c.product_name), '[\s\-]+', ' ', 'g')), 'пшеница') THEN 'Пшеница'
        WHEN regexp_matches(lower(regexp_replace(trim(c.product_name), '[\s\-]+', ' ', 'g')), 'мука') THEN 'Мука'
        WHEN regexp_matches(lower(regexp_replace(trim(c.product_name), '[\s\-]+', ' ', 'g')), 'дизельн') THEN 'Дизельное топливо'
        WHEN regexp_matches(lower(regexp_replace(trim(c.product_name), '[\s\-]+', ' ', 'g')), 'бензин') THEN 'Бензин'
        WHEN regexp_matches(lower(regexp_replace(trim(c.product_name), '[\s\-]+', ' ', 'g')), 'сжиж|пропан') THEN 'Сжиженный газ'
        WHEN regexp_matches(lower(regexp_replace(trim(c.product_name), '[\s\-]+', ' ', 'g')), 'сахар') THEN 'Сахар'
        WHEN regexp_matches(lower(regexp_replace(trim(c.product_name), '[\s\-]+', ' ', 'g')), 'трубы полиэтилен|труба пэ') THEN 'Трубы полиэтиленовые'
        WHEN regexp_matches(lower(regexp_replace(trim(c.product_name), '[\s\-]+', ' ', 'g')), 'полиэтилен') THEN 'Полиэтилен'
        WHEN regexp_matches(lower(regexp_replace(trim(c.product_name), '[\s\-]+', ' ', 'g')), 'полипропилен') THEN 'Полипропилен'
        WHEN regexp_matches(lower(regexp_replace(trim(c.product_name), '[\s\-]+', ' ', 'g')), 'поливинилхлорид') THEN 'Поливинилхлорид (ПВХ)'
        WHEN regexp_matches(lower(regexp_replace(trim(c.product_name), '[\s\-]+', ' ', 'g')), 'селитра') THEN 'Аммиачная селитра'
        WHEN regexp_matches(lower(regexp_replace(trim(c.product_name), '[\s\-]+', ' ', 'g')), 'карбамид|мочевина') THEN 'Карбамид'
        WHEN regexp_matches(lower(regexp_replace(trim(c.product_name), '[\s\-]+', ' ', 'g')), 'проволока') THEN 'Проволока арматурная'
        WHEN regexp_matches(lower(regexp_replace(trim(c.product_name), '[\s\-]+', ' ', 'g')), 'арматур') THEN 'Арматура'
        WHEN regexp_matches(lower(regexp_replace(trim(c.product_name), '[\s\-]+', ' ', 'g')), 'лист стальной') THEN 'Лист стальной'
        WHEN regexp_matches(lower(regexp_replace(trim(c.product_name), '[\s\-]+', ' ', 'g')), 'битум') THEN 'Битум'
        WHEN regexp_matches(lower(regexp_replace(trim(c.product_name), '[\s\-]+', ' ', 'g')), 'мазут') THEN 'Мазут'
        WHEN regexp_matches(lower(regexp_replace(trim(c.product_name), '[\s\-]+', ' ', 'g')), 'кирпич') THEN 'Кирпич'
        WHEN regexp_matches(lower(regexp_replace(trim(c.product_name), '[\s\-]+', ' ', 'g')), 'серная') THEN 'Серная кислота'
        WHEN regexp_matches(lower(regexp_replace(trim(c.product_name), '[\s\-]+', ' ', 'g')), 'подсолнечн') THEN 'Масло подсолнечное'
        WHEN regexp_matches(lower(regexp_replace(trim(c.product_name), '[\s\-]+', ' ', 'g')), 'кормосмесь|комбикорм') THEN 'Комбикорм'
        WHEN regexp_matches(lower(regexp_replace(trim(c.product_name), '[\s\-]+', ' ', 'g')), 'сода') THEN 'Сода каустическая'
        WHEN regexp_matches(lower(regexp_replace(trim(c.product_name), '[\s\-]+', ' ', 'g')), 'соль') THEN 'Соль'
        WHEN regexp_matches(lower(regexp_replace(trim(c.product_name), '[\s\-]+', ' ', 'g')), 'профиль') THEN 'Профиль алюминиевый'
        WHEN regexp_matches(lower(regexp_replace(trim(c.product_name), '[\s\-]+', ' ', 'g')), 'пиломатериал') THEN 'Пиломатериалы'
        WHEN regexp_matches(lower(regexp_replace(trim(c.product_name), '[\s\-]+', ' ', 'g')), 'катод') THEN 'Катод медный'
        WHEN regexp_matches(lower(regexp_replace(trim(c.product_name), '[\s\-]+', ' ', 'g')), 'кабель') THEN 'Кабель силовой'
        WHEN regexp_matches(lower(regexp_replace(trim(c.product_name), '[\s\-]+', ' ', 'g')), 'азот') THEN 'Азот'
        WHEN regexp_matches(lower(regexp_replace(trim(c.product_name), '[\s\-]+', ' ', 'g')), 'аргон') THEN 'Аргон'
        WHEN regexp_matches(lower(regexp_replace(trim(c.product_name), '[\s\-]+', ' ', 'g')), 'подшипник') THEN 'Подшипник'
        WHEN regexp_matches(lower(regexp_replace(trim(c.product_name), '[\s\-]+', ' ', 'g')), 'рис') THEN 'Рис'
        WHEN regexp_matches(lower(regexp_replace(trim(c.product_name), '[\s\-]+', ' ', 'g')), 'вода') THEN 'Вода питьевая'
        WHEN regexp_matches(lower(regexp_replace(trim(c.product_name), '[\s\-]+', ' ', 'g')), 'известь') THEN 'Известь'
        WHEN regexp_matches(lower(regexp_replace(trim(c.product_name), '[\s\-]+', ' ', 'g')), 'стекло') THEN 'Стекло'
        WHEN regexp_matches(lower(regexp_replace(trim(c.product_name), '[\s\-]+', ' ', 'g')), 'гипс') THEN 'Гипс'
        WHEN regexp_matches(lower(regexp_replace(trim(c.product_name), '[\s\-]+', ' ', 'g')), 'эмаль') THEN 'Эмаль'
        ELSE c.product_name
    END                                                 AS commodity,
    c.product_category                                  AS category,
    c.product_group,
    c.industry,
    c.commodity_code                                    AS tnved_code,
    d.measurement_unit_source                           AS unit,
    d.deal_quantity_lots::BIGINT                        AS lots,
    d.lot_size::BIGINT                                  AS lot_size,
    d.deal_quantity_lots::BIGINT * d.lot_size::BIGINT   AS quantity,
    d.delivered_lots::BIGINT * d.lot_size::BIGINT       AS delivered_quantity,
    d.currency,
    d.transaction_amount::DECIMAL(18,2)                 AS amount,
    d.starting_price::DECIMAL(18,2)                     AS start_price,
    round(d.transaction_amount::DOUBLE
          / (d.deal_quantity_lots::DOUBLE * d.lot_size::DOUBLE), 2) AS unit_price,
    d.usd_rate_on_deal_date::DECIMAL(18,2)              AS usd_rate,
    CASE WHEN d.currency = 'UZS' THEN d.transaction_amount::DECIMAL(18,2)
         ELSE round(d.transaction_amount::DECIMAL(18,2)
                    * d.usd_rate_on_deal_date::DECIMAL(18,2), 2)::DECIMAL(18,2)
    END                                                 AS amount_uzs,
    CASE WHEN d.currency = 'USD' THEN d.transaction_amount::DECIMAL(18,2)
         ELSE round(d.transaction_amount::DECIMAL(18,2)
                    / d.usd_rate_on_deal_date::DECIMAL(18,2), 2)::DECIMAL(18,2)
    END                                                 AS amount_usd,
    d.warehouse_region_source                           AS region,
    c.warehouse_region_source                           AS region_ru,
    d.seller_inn,
    s.company_name                                      AS seller_name,
    s.activity_source                                   AS seller_activity,
    d.buyer_inn,
    b.company_name                                      AS buyer_name,
    b.registration_region_source                        AS buyer_region,
    b.activity_source                                   AS buyer_activity,
    b.vat_payer_source                                  AS buyer_vat_payer,
    d.seller_broker_code                                AS seller_broker,
    sb.company_name                                     AS seller_broker_name,
    d.buyer_broker_code                                 AS buyer_broker,
    bb.company_name                                     AS buyer_broker_name,
    d.payment_date,
    d.delivery_date
FROM main.deals d
JOIN main.contracts c     ON c.contract_id = d.contract_id
JOIN main.participants s  ON s.inn = d.seller_inn
JOIN main.participants b  ON b.inn = d.buyer_inn
JOIN main.brokers sb      ON sb.broker_code = d.seller_broker_code
JOIN main.brokers bb      ON bb.broker_code = d.buyer_broker_code;

CREATE OR REPLACE TEMP VIEW companies AS
SELECT inn, company_name AS name, registration_region_source AS region,
       activity_source AS activity, role_source AS role,
       vat_payer_source AS vat_payer
FROM main.participants;

CREATE OR REPLACE TEMP VIEW broker_list AS
SELECT broker_code, company_name AS name, inn_source AS inn,
       registration_region_source AS region
FROM main.brokers;

CREATE OR REPLACE TEMP VIEW contract_list AS
SELECT contract_id::BIGINT AS contract_id, product_name AS product,
       lower(regexp_replace(trim(product_name), '[\s\-]+', ' ', 'g')) AS product_base,
       product_category AS category, industry, measurement_unit_source AS unit,
       lot_size::BIGINT AS lot_size, currency_source AS currency,
       base_price::DECIMAL(18,2) AS base_price, delivery_basis,
       warehouse_region_source AS region_ru, auction_type, contract_type,
       contract_form, seller_inn, registration_date, valid_until
FROM main.contracts;

CREATE OR REPLACE TEMP VIEW usd_rates_v AS
SELECT rate_date, usd_uzs_rate::DECIMAL(18,2) AS usd_uzs
FROM main.usd_rates;
"""

COMMODITIES = [
    "Хлопок-сырец",
    "Масло хлопковое",
    "Шрот хлопковый",
    "Пряжа хлопковая",
    "Цемент",
    "Пшеница",
    "Мука",
    "Дизельное топливо",
    "Бензин",
    "Сжиженный газ",
    "Сахар",
    "Трубы полиэтиленовые",
    "Полиэтилен",
    "Полипропилен",
    "Поливинилхлорид (ПВХ)",
    "Аммиачная селитра",
    "Карбамид",
    "Проволока арматурная",
    "Арматура",
    "Лист стальной",
    "Битум",
    "Мазут",
    "Кирпич",
    "Серная кислота",
    "Масло подсолнечное",
    "Комбикорм",
    "Сода каустическая",
    "Соль",
    "Профиль алюминиевый",
    "Пиломатериалы",
    "Катод медный",
    "Кабель силовой",
    "Азот",
    "Аргон",
    "Подшипник",
    "Рис",
    "Вода питьевая",
    "Известь",
    "Стекло",
    "Гипс",
    "Эмаль",
]

REGIONS = [
    ("Toshkent shahri", "г. Ташкент"),
    ("Toshkent viloyati", "Ташкентская обл."),
    ("Andijon viloyati", "Андижанская"),
    ("Buxoro viloyati", "Бухарская"),
    ("Farg‘ona viloyati", "Ферганская"),
    ("Jizzax viloyati", "Джизакская"),
    ("Namangan viloyati", "Наманганская"),
    ("Navoiy viloyati", "Навоийская"),
    ("Qashqadaryo viloyati", "Кашкадарьинская"),
    ("Qoraqalpog‘iston Respublikasi", "Каракалпакстан"),
    ("Samarqand viloyati", "Самаркандская"),
    ("Sirdaryo viloyati", "Сырдарьинская"),
    ("Surxondaryo viloyati", "Сурхандарьинская"),
    ("Xorazm viloyati", "Хорезмская"),
]

SCHEMA_PROMPT = """DuckDB views (synthetic UZEX commodity exchange data, deals 2022-01-03..2026-10-30, 500000 deals):

trades — one row per deal, all joins resolved:
 deal_id, deal_date DATE, year, month, quarter, deal_time TIME,
 auction_type: 'Английский аукцион'(English, price rises) | 'Двусторонний аукцион'(double) | 'Обратный аукцион'(reverse),
 contract_type: 'Внутренний'(domestic) | 'Экспортный'(export),
 contract_form: 'Спот' | 'Форвард' | 'Фьючерс',
 status: 'Исполнен'(executed) | 'Исполнен(Частично)'(partially executed) | 'Оплачен'(paid) | 'Заключен'(concluded) | 'Ждёт оплату'(awaiting payment) | 'Новый' | 'Не подписан' | 'Аннулирован(Не оплачен)'(cancelled, not paid),
 contract_id, commodity — product family, ALWAYS use it to filter/group products; exact values: {commodities}
 product (full source name incl. grade), product_norm (lowercase, '-'→space; use ILIKE on it for grades/brands like '%аи 92%', '%1 сорт%'), product_base (lowercase base name),
 category: 'Сельскохозяйственная продукция'|'Продовольственные товары'|'Строительные материалы'|'Нефтепродукты'|'Химическая продукция'|'Металлопродукция'|'Промышленные товары'|'Полимерная продукция',
 product_group: 'Высоколиквидные товары'|'Прочие товары', industry (Russian, e.g. 'Сельское хозяйство','Металлургия'), tnved_code,
 unit: 'тонна'|'килограмм'|'литр'|'штука'|'куб.метр'|'кв.метр'|'метр',
 lots (lots bought), lot_size (units per lot), quantity = lots*lot_size (physical volume in `unit`), delivered_quantity,
 currency: 'UZS' (493410 deals) | 'USD' (6590 export deals),
 amount DECIMAL — deal sum in its own currency; amount_uzs — sum in so'm (USD deals converted at the CBU rate of the deal date); amount_usd — sum in USD,
 start_price (starting price per unit), unit_price (= amount/quantity, executed price per unit, in deal currency), usd_rate (UZS per 1 USD on deal date),
 region — warehouse/seller region (exact values below), region_ru,
 seller_inn, seller_name, seller_activity, buyer_inn, buyer_name, buyer_region, buyer_activity, buyer_vat_payer('Да'|'Нет'),
 seller_broker (code 'BK001'..), seller_broker_name, buyer_broker, buyer_broker_name, payment_date, delivery_date
companies(inn, name, region, activity, role 'Продавец'|'Покупатель', vat_payer)
broker_list(broker_code, name, inn, region)
contract_list(contract_id, product, product_base, category, industry, unit, lot_size, currency, base_price, delivery_basis, region_ru, auction_type, contract_type, contract_form, seller_inn, registration_date, valid_until)
usd_rates_v(rate_date, usd_uzs) — daily CBU rate.
region values: {regions}
"""


def schema_prompt() -> str:
    regions = ", ".join(f"'{uz}'({ru})" for uz, ru in REGIONS)
    commodities = "|".join(f"'{c}'" for c in COMMODITIES)
    return SCHEMA_PROMPT.format(regions=regions, commodities=commodities)
