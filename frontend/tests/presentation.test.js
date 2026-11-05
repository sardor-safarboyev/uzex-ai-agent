import test from 'node:test';
import assert from 'node:assert/strict';
import { copy, formatNumber, formatAnswer, formatCell, columnUnit, unitLabel, formatWarning } from '../src/presentation.js';

function result(field, value, metadata = {}) {
  return {status:'answered', answer:'DO NOT DISPLAY 999999 transactions', execution:{returned_rows:1,
    result:{outcome:{data:{columns:[{field,...metadata}],rows:[[value]]}}}}};
}
test('natural Uzbek and Russian counts, including singular and plurals', () => {
  assert.equal(formatAnswer(result('deal_count',500000),'uz'),'Jami 500 000 ta bitim qayd etilgan.');
  assert.equal(formatAnswer(result('deal_count',500000),'ru'),'Всего зарегистрировано 500 000 сделок.');
  assert.equal(formatAnswer(result('deal_count',1),'ru'),'Всего зарегистрирована 1 сделка.');
  assert.match(formatAnswer(result('deal_count',22),'ru'),/22 сделки/);
});
test('decimal strings preserve every digit without floating-point conversion', () => {
  const exact = '1234567890123456789012345678.1234567890';
  assert.equal(formatNumber(exact,'uz'),'1 234 567 890 123 456 789 012 345 678,1234567890');
  assert.equal(formatNumber('-1234.1200','ru'),'-1 234,1200');
  assert.equal(formatNumber('1.234567890123456789E-7','uz'),'0,0000001234567890123456789');
  assert.equal(formatNumber('1E+10','ru'),'10 000 000 000');
  assert.equal(formatNumber(0,'uz'),'0');
});
test('currency codes remain exact and missing units are never invented', () => {
  assert.equal(formatAnswer(result('deal_value','123456.7890',{currency:'UZS'}),'uz'),'Jami summa: 123 456,7890 UZS.');
  assert.equal(formatAnswer(result('deal_value','123456.7890',{currency:'USD'}),'ru'),'Общая сумма: 123 456,7890 USD.');
  assert.equal(columnUnit({field:'physical_volume'},'uz'),'');
  assert.equal(columnUnit({field:'average_unit_price',currency:'USD',unit:'kg'},'ru'),'USD / кг');
});
test('supported units and lots are localized', () => {
  assert.equal(unitLabel('kg','ru'),'кг');
  assert.equal(unitLabel('tonne','uz'),'tonna');
  assert.equal(formatAnswer(result('physical_volume','1200.50',{unit:'tonne'}),'ru'),'Физический объём: 1 200,50 т.');
  assert.equal(formatAnswer(result('delivered_lots','21',{unit:'lots'}),'ru'),'Поставленные лоты: 21 лот.');
  assert.equal(formatAnswer(result('delivered_lots','22',{unit:'lots'}),'ru'),'Поставленные лоты: 22 лота.');
  assert.equal(unitLabel('unverified_source_unit','uz'),'unverified_source_unit');
});
test('product names, official statuses and identifiers remain exact', () => {
  for (const field of ['product','status','deal_id','seller_inn']) {
    assert.equal(formatCell('000123', {field}, 'ru'),'000123');
    assert.equal(formatCell('Paxta «A»', {field}, 'ru'),'Paxta «A»');
  }
  assert.equal(formatCell(null,{field:'physical_volume'},'uz'),'—');
  assert.equal(formatCell('fully_delivered',{field:'delivery_completion'},'ru'),'Поставлено полностью');
});
test('presentation never mutates structured numbers, warnings or evidence', () => {
  const value = result('deal_value','9007199254740993.123400',{currency:'UZS'});
  const original = JSON.stringify(value);
  for (const lang of ['uz','ru']) formatAnswer(value,lang);
  assert.equal(JSON.stringify(value),original);
  assert.equal(value.execution.result.outcome.data.rows[0][0],'9007199254740993.123400');
});
test('nonanswers remain localized and never display a model claim', () => {
  for (const lang of ['uz','ru']) for (const status of ['unsupported','ambiguous','no_match','insufficient_data','error']) {
    assert.equal(formatAnswer({status,answer:'The total is 999999'},lang),copy[lang][status]);
    assert.ok(!formatAnswer({status,answer:'The total is 999999'},lang).includes('999999'));
  }
});
test('coverage, disclaimers and warnings are bilingual without claiming completeness', () => {
  assert.equal(copy.uz.partial,'Qisman'); assert.equal(copy.ru.partial,'Частичный');
  assert.match(copy.uz.disclaimer,/sintetik/); assert.match(copy.ru.disclaimer,/Синтетические/);
  assert.match(copy.uz.disclaimer,/real yoki jonli.*emas/);
  assert.match(copy.ru.disclaimer,/Не являются реальными/);
  assert.equal(formatWarning('Source NULL values were retained and were not imputed.','ru'),'Пустые значения источника сохранены и не заменены предположениями.');
  assert.match(formatWarning('Currency/unit policy excluded 1200 source rows.','uz'),/1 200/);
  assert.equal(formatWarning('Future technical warning','ru'),copy.ru.extraWarning);
});
