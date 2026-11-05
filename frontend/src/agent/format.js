// Formatting helpers: safe mini-markdown and exact number grouping.

const escape = (s) => String(s)
  .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;').replaceAll("'", '&#39;');

function inline(text) {
  return escape(text)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[\s(])\*(?!\s)(.+?)\*(?=[\s).,;:!?]|$)/g, '$1<em>$2</em>')
    .replace(/(^|[\s(])_(?!\s)(.+?)_(?=[\s).,;:!?]|$)/g, '$1<em>$2</em>')
    .replace(/`([^`]+)`/g, '<code>$1</code>');
}

// Converts a small, trusted subset of markdown to HTML. All text is escaped first.
export function markdown(text) {
  const lines = String(text || '').replace(/\r/g, '').split('\n');
  const out = [];
  let list = null;
  const flush = () => { if (list) { out.push(`<${list.tag}>${list.items.join('')}</${list.tag}>`); list = null; } };
  for (const raw of lines) {
    const line = raw.trimEnd();
    const bullet = line.match(/^\s*[-*•]\s+(.*)$/);
    const numbered = line.match(/^\s*\d+[.)]\s+(.*)$/);
    if (bullet || numbered) {
      const tag = bullet ? 'ul' : 'ol';
      if (!list || list.tag !== tag) { flush(); list = { tag, items: [] }; }
      list.items.push(`<li>${inline((bullet || numbered)[1])}</li>`);
      continue;
    }
    flush();
    if (!line.trim()) continue;
    const heading = line.match(/^#{1,4}\s+(.*)$/);
    out.push(heading ? `<p><strong>${inline(heading[1])}</strong></p>` : `<p>${inline(line)}</p>`);
  }
  flush();
  return out.join('');
}

const NUMERIC = /^-?\d+(\.\d+)?$/;

export function isNumeric(value) {
  return typeof value === 'number' || (typeof value === 'string' && NUMERIC.test(value));
}

// Groups digits with thin spaces without converting to float (keeps exact cents).
export function formatNumber(value) {
  const text = String(value);
  if (!NUMERIC.test(text)) return text;
  const [int, frac] = text.split('.');
  const sign = int.startsWith('-') ? '-' : '';
  const digits = sign ? int.slice(1) : int;
  const grouped = digits.replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
  return sign + grouped + (frac ? ',' + frac.slice(0, 2).padEnd(Math.min(frac.length, 2), '0') : '');
}

export function formatCell(value, column = '') {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'boolean') return value ? '✓' : '✗';
  // ids, INN, years: no grouping
  if (/(^|_)(id|inn|year|code|month|quarter)$/i.test(column) || /^(year|month|quarter)$/i.test(column)) return String(value);
  if (isNumeric(value)) return formatNumber(value);
  if (Array.isArray(value)) return value.join(', ');
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

export function toCSV(result) {
  const cell = (v) => {
    const s = v === null || v === undefined ? '' : String(v);
    return /[",\n;]/.test(s) ? `"${s.replaceAll('"', '""')}"` : s;
  };
  return [result.columns.map(cell).join(','), ...result.rows.map((r) => r.map(cell).join(','))].join('\n');
}

// Picks (labelIndex, valueIndex) for a bar chart, or null.
export function chartSpec(result) {
  if (!result || !result.rows || result.rows.length < 2 || result.rows.length > 40) return null;
  const cols = result.columns;
  const numericCols = cols.map((_, i) => i).filter((i) => result.rows.every((r) => r[i] === null || isNumeric(r[i])));
  const labelIdx = cols.findIndex((_, i) => !numericCols.includes(i) || /^(year|month|quarter|yil|oy)$/i.test(cols[i]));
  if (labelIdx < 0) return null;
  const candidates = numericCols.filter((i) => i !== labelIdx && !/(^|_)(id|inn|year|month|quarter|rank)$/i.test(cols[i]));
  if (!candidates.length) return null;
  const preferred = candidates.find((i) => /amount|sum|summa|turnover|uzs|usd|value/i.test(cols[i]))
    ?? candidates.find((i) => /count|deals|cnt|num|n$/i.test(cols[i])) ?? candidates[0];
  return { labelIdx, valueIdx: preferred };
}
