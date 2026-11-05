import React, { useEffect, useRef, useState } from 'react';
import { UI, uiLang } from './i18n.js';
import { markdown, formatCell, formatNumber, toCSV, chartSpec } from './format.js';

const API = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const STORE = 'uzex.agent.chat.v2';

function load() {
  try { return JSON.parse(localStorage.getItem(STORE)) || []; } catch { return []; }
}

async function streamAsk(body, onEvent, signal) {
  const response = await fetch(`${API}/api/agent/stream`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal,
  });
  if (!response.ok || !response.body) {
    let data = null;
    try { data = await response.json(); } catch { /* ignore */ }
    throw Object.assign(new Error('http'), { data });
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let index;
    while ((index = buffer.indexOf('\n\n')) >= 0) {
      const chunk = buffer.slice(0, index);
      buffer = buffer.slice(index + 2);
      const line = chunk.split('\n').find((l) => l.startsWith('data: '));
      if (line) onEvent(JSON.parse(line.slice(6)));
    }
  }
}

function CopyButton({ text, t }) {
  const [done, setDone] = useState(false);
  return <button type="button" className="ghost small" onClick={() => {
    navigator.clipboard?.writeText(text).then(() => { setDone(true); setTimeout(() => setDone(false), 1200); });
  }}>{done ? t.copied : t.copy}</button>;
}

function BarChart({ result }) {
  const spec = chartSpec(result);
  if (!spec) return null;
  const rows = result.rows.slice(0, 15);
  const values = rows.map((r) => Math.abs(Number(r[spec.valueIdx]) || 0));
  const max = Math.max(...values) || 1;
  return <div className="chart" role="img" aria-label={result.columns[spec.valueIdx]}>
    <div className="chart-title">{result.columns[spec.valueIdx]}</div>
    {rows.map((r, i) => <div className="bar-row" key={i}>
      <span className="bar-label" title={String(r[spec.labelIdx])}>{formatCell(r[spec.labelIdx], result.columns[spec.labelIdx])}</span>
      <span className="bar-track"><span className="bar" style={{ width: `${Math.max(1.5, (values[i] / max) * 100)}%` }} /></span>
      <span className="bar-value">{formatNumber(r[spec.valueIdx])}</span>
    </div>)}
  </div>;
}

function ResultTable({ result, t }) {
  const download = () => {
    const blob = new Blob(['﻿' + toCSV(result)], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'uzex-result.csv';
    a.click();
    URL.revokeObjectURL(a.href);
  };
  return <div className="result-block">
    <div className="table-wrap"><table>
      <thead><tr>{result.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
      <tbody>{result.rows.map((row, i) => <tr key={i}>{row.map((v, j) => <td key={j} className={typeof v === 'number' || /^-?\d+(\.\d+)?$/.test(String(v)) ? 'num' : ''}>{formatCell(v, result.columns[j])}</td>)}</tr>)}</tbody>
    </table></div>
    <div className="table-meta">{result.row_count} {t.rows}{result.truncated ? ' +' : ''} · {result.ms} ms <button type="button" className="ghost small" onClick={download}>{t.csv}</button></div>
  </div>;
}

function Evidence({ data, t }) {
  const results = data.results || [];
  const models = [...new Set((data.trace || []).map((s) => s.model).filter(Boolean))];
  return <details className="evidence">
    <summary>{t.how}</summary>
    {data.understanding && <p className="understanding"><strong>{t.understanding}:</strong> {data.understanding}</p>}
    {(results.length ? results : data.queries || []).map((r, i) => <div key={i} className="query">
      <div className="query-head"><span>{t.query} {i + 1}{r.purpose ? ` — ${r.purpose}` : ''}</span><CopyButton text={r.sql} t={t} /></div>
      <pre className="sql"><code>{r.sql}</code></pre>
      {r.columns && <ResultTable result={r} t={t} />}
    </div>)}
    <div className="meta-line">
      {models.length > 0 && <span>{t.model}: {models.join(', ')}</span>}
      {data.timings && <span>{Object.entries(data.timings).map(([k, v]) => `${k.replace('_s', '')} ${v}${t.seconds}`).join(' · ')}</span>}
    </div>
  </details>;
}

function Answer({ message, t }) {
  const { data, stage, plan, partial } = message;
  if (!data) {
    return <div className="assistant pending">
      <div className="stages">
        {['planning', 'querying', 'answering'].map((s, i) => {
          const order = ['planning', 'querying', 'answering'].indexOf(stage);
          return <span key={s} className={i < order ? 'done' : i === order ? 'active' : ''}>{i < order ? '✓ ' : ''}{t.stages[s]}</span>;
        })}
      </div>
      {plan?.understanding && <p className="understanding">{plan.understanding}</p>}
      {plan?.queries?.map((sql, i) => <pre key={i} className="sql faded"><code>{sql}</code></pre>)}
      {partial?.map((r, i) => <ResultTable key={i} result={r} t={t} />)}
    </div>;
  }
  const v = data.verification;
  const chartResult = (data.results || []).find((r) => chartSpec(r));
  return <div className={`assistant ${data.status}`}>
    <div className="answer" dangerouslySetInnerHTML={{ __html: markdown(data.answer || t.error) }} />
    {data.status === 'answered' && chartResult && <BarChart result={chartResult} />}
    {data.status === 'answered' && v && (v.ok
      ? <div className="badge ok">✓ {v.checked ? t.verified(v.checked) : t.verifiedNone}{data.cached ? ` · ${t.cached}` : ''} · {data.timings?.total_s}{t.seconds}</div>
      : <div className="badge warn">⚠ {t.unverified(v.unverified.join(', '))}</div>)}
    {(data.queries?.length > 0) && <Evidence data={data} t={t} />}
  </div>;
}

export default function App() {
  const [lang, setLang] = useState(() => localStorage.getItem('uzex.ui.lang') || 'uz');
  const [messages, setMessages] = useState(load);
  const [question, setQuestion] = useState('');
  const [busy, setBusy] = useState(false);
  const [examples, setExamples] = useState([]);
  const bottom = useRef(null);
  const input = useRef(null);
  const controller = useRef(null);
  const t = UI[uiLang(lang)];

  useEffect(() => { document.documentElement.lang = lang; localStorage.setItem('uzex.ui.lang', lang); }, [lang]);
  useEffect(() => {
    try { localStorage.setItem(STORE, JSON.stringify(messages.filter((m) => m.role === 'user' || m.data).slice(-30))); } catch { /* quota */ }
    bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages]);
  useEffect(() => {
    fetch(`${API}/api/agent/examples`).then((r) => (r.ok ? r.json() : [])).then(setExamples).catch(() => {});
  }, []);

  const update = (id, patch) => setMessages((all) => all.map((m) => (m.id === id ? { ...m, ...(typeof patch === 'function' ? patch(m) : patch) } : m)));

  async function ask(text) {
    const q = (text ?? question).trim();
    if (!q || busy) return;
    setQuestion('');
    setBusy(true);
    const history = messages.filter((m) => m.role === 'assistant' && m.data?.status === 'answered').slice(-2)
      .map((m) => ({ question: m.data.question || '', sql: (m.data.queries || []).map((x) => x.sql).slice(0, 3) }));
    const id = `${Date.now()}`;
    setMessages((all) => [...all, { id: `u${id}`, role: 'user', text: q }, { id, role: 'assistant', stage: 'planning' }]);
    controller.current = new AbortController();
    const timeout = setTimeout(() => controller.current.abort(), 120000);
    try {
      await streamAsk({ question: q, language: 'auto', history }, (event) => {
        if (event.type === 'stage') update(id, { stage: event.stage });
        else if (event.type === 'plan') update(id, { plan: event });
        else if (event.type === 'results') update(id, { partial: event.results });
        else if (event.type === 'final') {
          update(id, { data: event.data });
          if (event.data?.language) setLang(event.data.language === 'ru' ? 'ru' : 'uz');
        }
      }, controller.current.signal);
      setMessages((all) => all.map((m) => (m.id === id && !m.data ? { ...m, data: { status: 'error', answer: t.error } } : m)));
    } catch (error) {
      update(id, { data: { status: 'error', answer: error?.data?.answer || t.network } });
    } finally {
      clearTimeout(timeout);
      setBusy(false);
      input.current?.focus();
    }
  }

  const reset = () => { if (!busy) { setMessages([]); localStorage.removeItem(STORE); } };
  const shown = examples.filter((e) => (lang === 'ru' ? e.lang === 'ru' : e.lang !== 'ru'));

  return <div className="shell">
    <header className="top">
      <div className="brand"><span className="logo">UZEX</span><div><h1>{t.title}</h1><p>{t.subtitle}</p></div></div>
      <div className="actions">
        <div className="lang-switch" role="group">
          {['uz', 'ru'].map((l) => <button type="button" key={l} className={uiLang(lang) === l ? 'on' : ''} onClick={() => setLang(l)}>{l === 'uz' ? 'O‘zbekcha' : 'Русский'}</button>)}
        </div>
        <button type="button" className="ghost" onClick={reset} disabled={busy}>{t.newChat}</button>
      </div>
    </header>

    <main className="thread">
      {messages.length === 0 && <section className="welcome">
        <p className="disclaimer">{t.disclaimer}</p>
        <h2>{t.examples}</h2>
        <div className="examples">{(shown.length ? shown : examples).map((e) => <button type="button" key={e.q} onClick={() => ask(e.q)}>{e.q}</button>)}</div>
        <p className="hint">{t.followup}</p>
      </section>}
      {messages.map((m) => (m.role === 'user'
        ? <div key={m.id} className="user"><div className="bubble">{m.text}</div></div>
        : <Answer key={m.id} message={m} t={t} />))}
      <div ref={bottom} />
    </main>

    <form className="composer" onSubmit={(e) => { e.preventDefault(); ask(); }}>
      <textarea ref={input} value={question} rows={1} maxLength={2000} placeholder={t.placeholder}
        onChange={(e) => setQuestion(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask(); } }} />
      <button type="submit" disabled={busy || !question.trim()}>{busy ? <span className="spinner" /> : t.send}</button>
    </form>
  </div>;
}
