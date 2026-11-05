import test from 'node:test';
import assert from 'node:assert/strict';
import {resultLanguage, showCoverage, coverageLabel} from './presentation.js';

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
