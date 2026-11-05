import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';
import { copy, title as fieldTitle, formatNumber, formatCell, columnHeader, columnHeaderUnit, partitionWarnings, formatAnswer, formatWarning, resultLanguage, showCoverage, coverageLabel } from './presentation.js';

const API = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
function App() {
  const [lang,setLang] = useState('uz');
  const [languageMode,setLanguageMode] = useState('auto');
  const [question,setQuestion] = useState('');
  const [examples,setExamples] = useState([]);
  const [busy,setBusy] = useState(false);
  const [result,setResult] = useState(null);
  const [error,setError] = useState('');
  const resultRef = useRef(null);
  const pending = useRef(false);
  const controller = useRef(null);
  const effectiveLang = languageMode === 'auto' ? resultLanguage(result, lang) : lang;
  const t = copy[effectiveLang];
  useEffect(() => {
    if (busy || result || error) {
      resultRef.current?.scrollIntoView({block:'start'});
      if (!busy) resultRef.current?.focus({preventScroll:true});
    }
  }, [busy,result,error]);
  useEffect(() => { document.documentElement.lang = effectiveLang; }, [effectiveLang]);
  useEffect(() => {
    const abort = new AbortController();
    fetch(`${API}/api/examples`,{signal:abort.signal}).then(r => r.ok ? r.json() : []).then(data => setExamples(Array.isArray(data) ? data : [])).catch(() => {});
    return () => { abort.abort(); controller.current?.abort(); };
  }, []);
  async function submit(event) {
    event.preventDefault();
    if (pending.current) return;
    if (!question.trim() || question.length > 4000) { setError('invalid'); return; }
    pending.current = true; setBusy(true); setError(''); setResult(null);
    controller.current = new AbortController();
    const timeout = setTimeout(() => controller.current.abort(), 180000);
    try {
      const response = await fetch(`${API}/api/ask`, {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({question:question.trim(),language:languageMode}), signal:controller.current.signal,
      });
      const data = await response.json();
      if (data.status && typeof data.answer === 'string') setResult(data);
      else setError(response.status === 422 ? 'invalid' : 'failure');
    } catch { setError('network'); }
    finally { clearTimeout(timeout); pending.current = false; setBusy(false); }
  }
  const execution = result?.execution;
  const data = execution?.result?.outcome?.data;
  const coverage = execution?.result?.coverage;
  const {routine,important} = partitionWarnings(execution?.warnings);
  const title = field => fieldTitle(field,effectiveLang);
  return <div className="shell">
    <header><a className="brand" href="/" aria-label={t.home}><span className="mark">U</span><span>UZEX<span className="brand-sub">AI Agent</span></span></a><div className="languages" aria-label={t.language}>{['auto','uz','ru'].map(l=><button key={l} aria-pressed={languageMode===l} onClick={()=>{setLanguageMode(l);if(l!=='auto')setLang(l);}} disabled={busy}>{l==='auto'?'Auto':l==='uz'?'O‘zbekcha':'Русский'}</button>)}</div></header>
    <p className="disclaimer">{t.disclaimer}</p>
    <main><section className="hero"><p className="eyebrow">{t.kicker}</p><h1>{t.title}</h1><p className="intro">{t.intro}</p></section>
    <div className="workspace"><section className="question-card"><form onSubmit={submit}><label htmlFor="question">{t.label}</label><textarea id="question" value={question} onChange={e=>setQuestion(e.target.value)} maxLength={4000} placeholder={t.placeholder} disabled={busy} rows={5} required/><div className="input-footer"><span>{question.length}/4000</span><button className="primary" type="submit" disabled={busy||!question.trim()}>{busy?'…':t.ask}<span aria-hidden="true"> ↗</span></button></div><p className="hint">{t.hint}</p></form><div className="examples"><h2>{t.examples}</h2>{examples.map(e=><button key={e.id} onClick={()=>{setQuestion(e[effectiveLang]);document.getElementById('question')?.focus();}} disabled={busy}>{e[effectiveLang]}<span aria-hidden="true">↗</span></button>)}</div></section>
    <section ref={resultRef} tabIndex={-1} className={`result-card${!busy&&(error||(result&&result.status!=='answered'))?' compact':''}`} aria-label={t.result} aria-live="polite" aria-busy={busy}>
      {busy?<div className="empty"><span className="empty-symbol">···</span><h2>{t.loading}</h2></div>:error?<div role="alert" className="notice error">{t[error] || t.failure}</div>:!result?<div className="empty"><span className="empty-symbol">↗</span><h2>{t.empty}</h2><p>{t.emptyBody}</p></div>:<>
        <div className="result-heading"><p className="eyebrow">{t.result}</p><span className={`badge ${result.status==='answered'?'success':''}`}>{t.statuses[result.status]||t.failure}</span></div>
        <h2 className="answer" role={result.status==='error'?'alert':undefined}>{formatAnswer(result,effectiveLang)}</h2>
        {result.status==='answered'&&coverage?.state==='complete'&&<p className="verified">✓ {t.verify}</p>}
        {result.status==='answered'&&data?.rows?.length>0&&<div className="table-wrap"><table><caption>{t.table}</caption><thead><tr>{data.columns.map(c=><th key={c.field}>{columnHeader(c,execution,effectiveLang)}{columnHeaderUnit(c,effectiveLang)&&<small>{columnHeaderUnit(c,effectiveLang)}</small>}</th>)}</tr></thead><tbody>{data.rows.map((row,i)=><tr key={i}>{row.map((v,j)=><td key={j}>{formatCell(v,data.columns[j],effectiveLang)}</td>)}</tr>)}</tbody></table></div>}
        {execution?.truncated&&<p className="notice">{t.truncated}</p>}
        {!!important.length&&<div className="notice"><strong>{t.warnings}</strong><ul>{important.map((w,i)=><li key={i}>{formatWarning(w,effectiveLang)}</li>)}</ul></div>}
        {showCoverage(coverage)&&<section className="evidence"><h3>{t.coverageSummary}</h3><div className="coverage">{coverage.matched_rows!=null&&<div><span>{t.matched}</span><strong>{formatNumber(coverage.matched_rows,effectiveLang)}</strong></div>}{coverage.evaluated_rows!=null&&<div><span>{t.evaluated}</span><strong>{formatNumber(coverage.evaluated_rows,effectiveLang)}</strong></div>}<div><span>{t.coverage}</span><strong>{coverageLabel(coverage.state,effectiveLang)}</strong></div></div>{coverage.issues?.map((v,i)=><p className="notice" key={i}>{t.issues[v.code] || t.issues.other}</p>)}</section>}
        {(execution?.result?.evidence?.length>0||execution?.provenance?.length>0||routine.length>0)&&<details id="evidence-details"><summary>{t.evidence}</summary>
          {!!routine.length&&<div className="notice"><strong>{t.warnings}</strong><ul>{routine.map((w,i)=><li key={i}>{formatWarning(w,effectiveLang)}</li>)}</ul></div>}
          {!!execution.result.evidence.length&&<div className="table-wrap"><table><thead><tr><th>{t.source}</th><th>{t.version}</th><th>{t.fields}</th></tr></thead><tbody>{execution.result.evidence.map((e,i)=><tr key={i}><td>{e.source_id}</td><td className="hash">{e.dataset_version}</td><td>{e.logical_fields.map(title).join(', ')}</td></tr>)}</tbody></table></div>}
          {!!execution.provenance?.length&&<><h3>{t.provenance}</h3><div className="table-wrap"><table><thead><tr><th>{t.row}</th><th>{t.source}</th><th>{t.record}</th></tr></thead><tbody>{execution.provenance.map((p,i)=><tr key={i}><td>{p.row}</td><td>{p.source_file}</td><td>{p.source_record}</td></tr>)}</tbody></table></div></>}
          <details><summary>{t.raw}</summary><pre>{JSON.stringify(execution,null,2)}</pre></details>
        </details>}
      </>}
    </section></div></main><footer><span>UZEX AI Agent</span><span>O‘zbekcha · Русский</span></footer>
  </div>;
}
createRoot(document.getElementById('root')).render(<App/>);
