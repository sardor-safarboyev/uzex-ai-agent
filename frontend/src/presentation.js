export const copy = {
  uz: {
    kicker: 'SAVDO MA’LUMOTLARI YORDAMCHISI', title: 'Savolingizdan aniq natijaga.',
    intro: 'UZEX bitimlarini o‘zbek yoki rus tilida o‘rganing. Javoblar manba ma’lumotlaridan hisoblanadi.',
    label: 'Nimani bilmoqchisiz?', placeholder: 'Masalan: 2024-yilda bitimlar soni qancha?',
    ask: 'So‘rash', loading: 'So‘rov tekshirilmoqda va hisoblanmoqda…', examples: 'Boshlash uchun savollar',
    hint: 'Aniq sana, valyuta va mahsulot nomini ko‘rsating.', empty: 'Birinchi savolingizni bering',
    emptyBody: 'Natija, tekshirilgan so‘rov doirasi va manbalar shu yerda paydo bo‘ladi.',
    result: 'NATIJA', table: 'Natija jadvali', evidence: 'Manbalar va qamrov', scope: 'So‘rov doirasi',
    matched: 'Mos bitimlar', evaluated: 'Tekshirilgan bitimlar', source: 'Manba', version: 'Versiya / SHA-256',
    fields: 'Maydonlar', warnings: 'Izohlar', coverage: 'Qamrov', truncated: 'Natija cheklangan. So‘rovni toraytiring.',
    network: 'Serverga ulanib bo‘lmadi yoki so‘rov vaqti tugadi. Qayta urinib ko‘ring.',
    invalid: 'Savol 1–4000 belgidan iborat bo‘lishi kerak.', verify: 'Manba asosida hisoblangan',
    provenance: 'Qator manbasi', period: 'Davr qamrovi', failure: 'So‘rov bajarilmadi.',
    statuses: {answered:'Hisoblandi', no_match:'Mos bitim yo‘q', ambiguous:'Aniqlashtirish kerak', unsupported:'Qo‘llanmaydi', insufficient_data:'Ma’lumot yetarli emas', error:'Xatolik'},
    errors: {configuration:'Xizmat hozir mavjud emas.', provider_error:'Til xizmati mavjud emas. Keyinroq urinib ko‘ring.', rate_limit:'Xizmat band. Birozdan so‘ng urinib ko‘ring.', timeout:'Til xizmati javob bermadi. Qayta urinib ko‘ring.', invalid_response:'Savolni boshqacha ifodalab ko‘ring.', busy:'Server band. Birozdan so‘ng urinib ko‘ring.', execution_failed:'Ma’lumotlar bazasiga so‘rov bajarilmadi.', internal_error:'So‘rovni xavfsiz bajarib bo‘lmadi.'},
  },
  ru: {
    kicker: 'ПОМОЩНИК ПО ТОРГОВЫМ ДАННЫМ', title: 'От вопроса к точному результату.',
    intro: 'Исследуйте сделки UZEX на узбекском или русском языке. Ответы рассчитываются по исходным данным.',
    label: 'Что вы хотите узнать?', placeholder: 'Например: сколько сделок за 2024 год?',
    ask: 'Спросить', loading: 'Проверяем запрос и рассчитываем результат…', examples: 'Попробуйте спросить',
    hint: 'Укажите точные даты, валюту и название товара.', empty: 'Задайте первый вопрос',
    emptyBody: 'Здесь появятся результат, проверенные параметры запроса и источники.',
    result: 'РЕЗУЛЬТАТ', table: 'Таблица результатов', evidence: 'Источники и охват', scope: 'Параметры запроса',
    matched: 'Подходящих сделок', evaluated: 'Проверено сделок', source: 'Источник', version: 'Версия / SHA-256',
    fields: 'Поля', warnings: 'Примечания', coverage: 'Охват', truncated: 'Результат ограничен. Сузьте запрос.',
    network: 'Не удалось связаться с сервером или истекло время ожидания. Попробуйте снова.',
    invalid: 'Вопрос должен содержать от 1 до 4000 символов.', verify: 'Рассчитано по источникам',
    provenance: 'Источник строки', period: 'Охват периодов', failure:'Запрос не выполнен.',
    statuses: {answered:'Рассчитано', no_match:'Сделки не найдены', ambiguous:'Нужно уточнение', unsupported:'Не поддерживается', insufficient_data:'Недостаточно данных', error:'Ошибка'},
    errors: {configuration:'Сервис сейчас недоступен.', provider_error:'Языковой сервис недоступен. Попробуйте позже.', rate_limit:'Сервис занят. Повторите попытку позже.', timeout:'Языковой сервис не ответил. Попробуйте снова.', invalid_response:'Попробуйте переформулировать вопрос.', busy:'Сервер занят. Повторите попытку позже.', execution_failed:'Не удалось выполнить запрос к базе.', internal_error:'Не удалось безопасно выполнить запрос.'},
  },
};
const labels = {
  deal_year: ['Yil','Год'],
  deal_count: ['Bitimlar soni','Количество сделок'], deal_value:['Jami summa','Общая сумма'],
  warehouse_region:['Ombor viloyati','Регион склада'], product:['Mahsulot','Товар'],
  status:['Rasmiy holat','Официальный статус'], delivery_completion:['Yetkazib berish','Поставка'],
  currency:['Valyuta','Валюта'], measurement_unit:['O‘lchov birligi','Единица'],
  physical_volume:['Jismoniy hajm','Физический объём'], delivered_lots:['Yetkazilgan lotlar','Поставленные лоты'],
  deal_id:['Bitim raqami','Номер сделки'], deal_date:['Sana','Дата'],
  baseline:['Oldingi davr','Базовый период'], target:['Keyingi davr','Целевой период'],
  absolute_difference:['Farq','Разница'], percentage_change:['O‘zgarish','Изменение'],
};

Object.assign(copy.uz, {
  intro: 'Sintetik bitimlar to‘plamini o‘zbek yoki rus tilida o‘rganing. Javoblar ushbu namoyish ma’lumotlaridan hisoblanadi.',
  disclaimer: "Namoyish uchun yaratilgan sintetik ma'lumotlar. UZEXning real yoki jonli savdo ma'lumotlari emas.",
  evidence: 'Manbalar va tekshiruv', coverageSummary: 'Natija qamrovi', raw: 'Asl texnik tafsilotlar',
  home: 'Bosh sahifa', language: 'Til', row: 'Qator', record: 'Manbadagi yozuv',
  rows: 'Natija: {count} qator. Tafsilotlar quyida.',
  complete: 'To‘liq', partial: 'Qisman', unknown: 'Noma’lum', unavailable: 'Mavjud emas',
  answered: 'Natija jadvalda keltirilgan.', no_match: 'So‘rovga mos bitim topilmadi.',
  insufficient_data: 'Aniq javob uchun ma’lumot yetarli emas.',
  ambiguous: 'So‘rov, sana, valyuta, o‘lchov birligi yoki aniq nomni aniqlashtiring.',
  unsupported: 'Bu so‘rov tasdiqlangan qoidalar bilan qo‘llanmaydi.',
  error: 'So‘rov bajarilmadi. Qayta urinib ko‘ring yoki sozlamalarni tekshiring.',
  extraWarning: 'Qo‘shimcha texnik izoh mavjud. Asl tafsilotlarni manbalar bo‘limida ko‘ring.',
  issues: {missing_rate:'Valyuta kursi yetishmaydi.', unverified_mapping:'Kerakli moslik tasdiqlanmagan.', missing_values:'Hisoblash uchun ayrim qiymatlar yetishmaydi.', duplicate_id:'Takroriy identifikator aniqlangan.', zero_baseline:'Bazaviy qiymat nol: foiz o‘zgarishi aniqlanmagan.', zero_denominator:'Maxraj nol: tegishli nisbat aniqlanmagan.', other:'Qamrovga oid cheklov mavjud. Asl tafsilotlarni ko‘ring.'},
});
Object.assign(copy.ru, {
  intro: 'Исследуйте набор синтетических сделок на узбекском или русском языке. Ответы рассчитываются по демонстрационным данным.',
  disclaimer: 'Синтетические данные для демонстрации. Не являются реальными или актуальными торговыми данными UZEX.',
  evidence: 'Источники и проверка', coverageSummary: 'Охват результата', raw: 'Исходные технические сведения',
  home: 'Главная', language: 'Язык', row: 'Строка', record: 'Запись в источнике',
  rows: 'Результат: строк — {count}. Данные ниже.',
  complete: 'Полный', partial: 'Частичный', unknown: 'Неизвестен', unavailable: 'Недоступен',
  answered: 'Результат приведён в таблице.', no_match:'Сделки по этому запросу не найдены.',
  insufficient_data:'Недостаточно данных для достоверного ответа.',
  ambiguous:'Уточните запрос, даты, валюту, единицу или точное название.',
  unsupported:'Запрос не поддерживается проверенными правилами.',
  error:'Запрос не выполнен. Повторите попытку или проверьте настройки.',
  extraWarning: 'Есть дополнительное техническое примечание. Исходный текст доступен в разделе источников.',
  issues: {missing_rate:'Отсутствует валютный курс.', unverified_mapping:'Нужное соответствие не подтверждено.', missing_values:'Для расчёта не хватает некоторых значений.', duplicate_id:'Обнаружен повторяющийся идентификатор.', zero_baseline:'Базовое значение равно нулю: процентное изменение не определено.', zero_denominator:'Знаменатель равен нулю: отношение не определено.', other:'Есть ограничение охвата. См. исходные сведения.'},
});
copy.uz.errors.invalid_input = copy.uz.invalid;
copy.ru.errors.invalid_input = copy.ru.invalid;
copy.uz.errors.validation_failed = 'So‘rov rejasini tekshirib bo‘lmadi.';
copy.ru.errors.validation_failed = 'Не удалось проверить план запроса.';
copy.uz.errors.invalid_response = 'Til xizmati yaroqli so‘rov rejasini qaytarmadi. Savolni aniqroq yozing.';
copy.ru.errors.invalid_response = 'Языковой сервис вернул некорректный план. Уточните вопрос.';
Object.assign(labels, {
  average_unit_price:['O‘rtacha birlik narxi','Средняя цена за единицу'],
  seller_inn:['Sotuvchi STIR','ИНН продавца'], buyer_inn:['Xaridor STIR','ИНН покупателя'],
  seller_broker_code:['Sotuvchi brokeri kodi','Код брокера продавца'], buyer_broker_code:['Xaridor brokeri kodi','Код брокера покупателя'],
  product_id:['Mahsulot identifikatori','Идентификатор товара'], contract_type:['Shartnoma turi','Тип контракта'],
  contract_form:['Shartnoma shakli','Форма контракта'], deal_quantity_lots:['Bitim lotlari','Лоты сделки'],
  lot_size:['Lot hajmi','Размер лота'], transaction_amount:['Bitim summasi','Сумма сделки'],
  executed_unit_price:['Ijro birlik narxi','Цена исполнения за единицу'],
});
export function title(field, lang) { return labels[field]?.[lang === 'uz' ? 0 : 1] || field; }

// Decimal strings stay strings: no parseFloat, rounding, or precision loss.
export function formatNumber(value, lang = 'uz') {
  const text = String(value);
  const match = text.match(/^([+-]?)(\d+)(?:\.(\d*))?(?:[eE]([+-]?\d+))?$/);
  if (!match) return text;
  let [, sign, whole, fraction = '', exponent = '0'] = match;
  const shift = Number(exponent);
  if (Math.abs(shift) > 1000) return text;
  if (shift) {
    const digits = whole + fraction;
    const point = whole.length + shift;
    if (point <= 0) { whole = '0'; fraction = '0'.repeat(-point) + digits; }
    else if (point >= digits.length) { whole = digits + '0'.repeat(point - digits.length); fraction = ''; }
    else { whole = digits.slice(0, point); fraction = digits.slice(point); }
  }
  return sign + whole.replace(/\B(?=(\d{3})+(?!\d))/g, ' ') + (fraction ? ',' + fraction : '');
}
function plural(value, forms) {
  const text = String(value);
  if (!/^\d+$/.test(text)) return forms[1];
  const n = BigInt(text), last = n % 10n, pair = n % 100n;
  return forms[pair >= 11n && pair <= 14n ? 2 : last === 1n ? 0 : last >= 2n && last <= 4n ? 1 : 2];
}
export function unitLabel(unit, lang, value = null) {
  const units = {
    kg:['kg','кг'], tonne:['tonna','т'], litre:['litr','л'], cubic_metre:['m³','м³'],
    piece:['dona','шт.'], lots:['lot','лоты'], transactions:['ta bitim','сделки'], percent:['%','%'],
  };
  if (lang === 'ru' && value !== null && unit === 'lots') return plural(value,['лот','лота','лотов']);
  if (lang === 'ru' && value !== null && unit === 'transactions') return plural(value,['сделка','сделки','сделок']);
  return units[unit]?.[lang === 'uz' ? 0 : 1] || unit;
}
export function columnUnit(column, lang, value = null) {
  const currency = column.currency || '';
  const unit = column.unit ? unitLabel(column.unit,lang,value) : '';
  const price = ['average_unit_price','executed_unit_price'].includes(column.metric || column.field);
  return [currency,unit].filter(Boolean).join(price ? ' / ' : ' ');
}
const numeric = new Set(['deal_count','deal_value','physical_volume','delivered_lots','average_unit_price','deal_quantity_lots','transaction_amount','executed_unit_price','lot_size','baseline','target','absolute_difference','percentage_change']);
export function formatCell(value, column, lang) {
  if (value === null || value === undefined) return '—';
  if (numeric.has(column.field)) return formatNumber(value,lang);
  if (column.field === 'measurement_unit') return unitLabel(value,lang);
  if (column.field === 'delivery_completion') {
    const values = {fully_delivered:['To‘liq yetkazilgan','Поставлено полностью'], partially_delivered:['Qisman yetkazilgan','Поставлено частично'],not_delivered:['Yetkazilmagan','Не поставлено']};
    return values[value]?.[lang === 'uz' ? 0 : 1] || String(value);
  }
  // Official status, product names, identifiers and other source text are exact.
  return String(value);
}
export function formatAnswer(result, lang) {
  const t = copy[lang];
  if (result.status !== 'answered') {
    if (result.status === 'error') return t.errors[result.error] || t.error;
    return nonanswerReasons[lang][result.reason] || t[result.status] || t.failure;
  }
  const data = result.execution?.result?.outcome?.data;
  if (data?.rows?.length === 1 && data.columns.length === 1) {
    const column = data.columns[0], value = data.rows[0][0];
    if (value !== null && value !== undefined) {
      const formatted = formatCell(value,column,lang);
      if (column.field === 'deal_count') {
        if (lang === 'uz') return `Jami ${formatted} ta bitim qayd etilgan.`;
        const noun = plural(value,['сделка','сделки','сделок']);
        return `Всего ${noun === 'сделка' ? 'зарегистрирована' : 'зарегистрировано'} ${formatted} ${noun}.`;
      }
      const suffix = columnUnit(column,lang,value);
      return `${title(column.field,lang)}: ${formatted}${suffix ? ' ' + suffix : ''}.`;
    }
  }
  return t.rows.replace('{count}', formatNumber(data?.rows?.length ?? result.execution?.returned_rows ?? 0,lang));
}
export function formatWarning(text, lang) {
  const warnings = [
    ['Ratios use Decimal precision 38, ROUND_HALF_EVEN; no FX conversion is performed.', 'Nisbatlar 38 xonali aniqlikda, ROUND_HALF_EVEN bilan ifodalanadi; valyuta konvertatsiyasi bajarilmaydi.', 'Отношения представлены с точностью 38 цифр и ROUND_HALF_EVEN; валютная конвертация не выполняется.'],
    ['Source NULL values were retained and were not imputed.', 'Manbadagi bo‘sh qiymatlar saqlangan; ular taxmin bilan to‘ldirilmagan.', 'Пустые значения источника сохранены и не заменены предположениями.'],
    ['The result limit was reduced to the configured server maximum.', 'Natija hajmi serverda belgilangan eng katta miqdor bilan cheklangan.', 'Размер результата ограничен настроенным максимумом сервера.'],
    ['Additional groups exist beyond the result limit; coverage counts include the full matching population.', 'Chegaradan tashqarida qo‘shimcha guruhlar bor; qamrov sonlari barcha mos bitimlarni qamrab oladi.', 'За пределами лимита есть другие группы; показатели охвата учитывают все подходящие сделки.'],
    ['Text predicates use SQL NULL semantics; NULL values do not match eq/ne/in/not_in.', 'Matn filtrlari bo‘sh qiymatlarni mos deb hisoblamaydi (eq/ne/in/not_in).', 'Текстовые фильтры не считают пустые значения совпадениями (eq/ne/in/not_in).'],
  ];
  const found = warnings.find(row=>row[0]===text);
  if (found) return found[lang === 'uz' ? 1 : 2];
  const match = text.match(/^Currency\/unit policy excluded (\d+) source rows\.$/);
  if (match) return lang === 'uz' ? `Valyuta yoki birlik siyosati ${formatNumber(match[1],lang)} ta manba qatorini chiqarib tashlagan.` : `Валютная политика или политика единиц исключила ${formatNumber(match[1],lang)} строк источника.`;
  return copy[lang].extraWarning;
}

export function resultLanguage(result, fallback) {
  return ['uz', 'ru'].includes(result?.language) ? result.language : fallback;
}
export function showCoverage(coverage) {
  return coverage?.evaluated_rows != null;
}
export function coverageLabel(state, language) {
  return ({
    uz: {complete:'To‘liq', partial:'Qisman', unknown:'Aniqlanmagan', unavailable:'Mavjud emas'},
    ru: {complete:'Полный', partial:'Частичный', unknown:'Не определён', unavailable:'Недоступен'},
  })[language][state] || '—';
}

const nonanswerReasons = {
  "uz": {
    "currency_conversion": "USD dan UZS ga o‘tkazish qo‘llanmaydi: kursni qo‘llash va yaxlitlash qoidalari tasdiqlanmagan.",
    "unverified_mapping": "Nom yoki identifikator mosligi tasdiqlanmagan. Manbadagi aniq nomni ko‘rsating.",
    "unavailable_data": "Bu so‘rov uchun kerakli ma’lumot mavjud emas.",
    "unsupported_unit": "So‘ralgan o‘lchov birligi yoki birliklarni o‘tkazish qoidasi tasdiqlanmagan.",
    "unsupported_date": "Bu sana filtri qo‘llanmaydi. Aniq boshlanish va tugash sanalarini ko‘rsating.",
    "currency": "Qaysi valyuta kerak: USD yoki UZS?",
    "ambiguous_metric": "Qaysi mezon kerak: bitimlar soni yoki jismoniy hajm?",
    "unit": "Qaysi o‘lchov birligi kerak?"
  },
  "ru": {
    "currency_conversion": "Перевод USD в UZS не поддерживается: правила применения курса и округления не проверены.",
    "unverified_mapping": "Соответствие названия или идентификатора не проверено. Укажите точное название из источника.",
    "unavailable_data": "Данные, необходимые для этого запроса, отсутствуют.",
    "unsupported_unit": "Запрошенная единица или правила пересчёта единиц не проверены.",
    "unsupported_date": "Этот фильтр дат не поддерживается. Укажите точные даты начала и окончания.",
    "currency": "Какая валюта нужна: USD или UZS?",
    "ambiguous_metric": "По какому показателю: количеству сделок или физическому объёму?",
    "unit": "Какая единица измерения нужна?"
  }
};
