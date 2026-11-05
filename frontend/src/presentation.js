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
