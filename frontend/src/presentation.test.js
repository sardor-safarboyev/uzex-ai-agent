import test from 'node:test';
import assert from 'node:assert/strict';
import {resultLanguage, showCoverage, coverageLabel, title, formatAnswer} from './presentation.js';

test('result language controls labels independently of UI language', () => {
  assert.equal(resultLanguage({language:'ru'}, 'uz'), 'ru');
  assert.equal(resultLanguage({language:'uz'}, 'ru'), 'uz');
  assert.equal(resultLanguage(null, 'uz'), 'uz');
  assert.equal(coverageLabel('complete', 'ru'), 'Полный');
  assert.equal(coverageLabel('complete', 'uz'), 'To‘liq');
});
test('nonexecuted requests do not show unknown coverage as a failure', () => {
  assert.equal(showCoverage({state:'unknown', evaluated_rows:null}), false);
  assert.equal(showCoverage(undefined), false);
  assert.equal(showCoverage({state:'complete', evaluated_rows:0}), true);
});
test('year grouping and analytical clarifications are bilingual', () => {
  assert.equal(title('deal_year', 'uz'), 'Yil');
  assert.equal(title('deal_year', 'ru'), 'Год');
  assert.match(formatAnswer({status:'ambiguous', reason:'ambiguous_metric'}, 'uz'), /bitimlar soni/);
  assert.match(formatAnswer({status:'ambiguous', reason:'ambiguous_metric'}, 'ru'), /количеству сделок/);
  assert.match(formatAnswer({status:'error', error:'invalid_response'}, 'ru'), /некорректный план/);
});
test('currency comparison summaries use real values and preserve scope', () => {
  const result={status:'answered',execution:{scope:{request:{kind:'comparison',baseline:{start:'2024-01-01',end:'2024-12-31'},target:{start:'2025-01-01',end:'2025-12-31'},aggregate:{metrics:['deal_count'],money:{mode:'source',source_currency:'UZS'}}}},result:{outcome:{data:{columns:[{field:'baseline'},{field:'target'},{field:'absolute_difference'}],rows:[[105320,114396,9076]]}}}}};
  const before=JSON.stringify(result);
  for(const lang of ['uz','ru']) {
    const text=formatAnswer(result,lang);
    assert.match(text,/105 320/);assert.match(text,/114 396/);assert.match(text,/9 076/);
    assert.match(text,/UZS/);assert.match(text,/2025/);
    assert.ok(!text.includes('qator')&&!text.includes('строк'));
  }
  assert.equal(JSON.stringify(result),before);
});
test('availability messages use supplied metadata and stay bilingual', () => {
  const result={status:'insufficient_data',reason:'outside_coverage',availability:{available_years:[2022,2023,2024,2025,2026],missing_years:[2028]}};
  assert.match(formatAnswer(result,'uz'),/2028-yil.*mavjud emas/);
  assert.match(formatAnswer(result,'ru'),/Данных.*2028/);
  assert.match(formatAnswer({...result,availability:{available_years:[2019,2020],missing_years:[2028]}},'ru'),/2019–2020/);
});
