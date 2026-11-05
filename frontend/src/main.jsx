import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';
import { copy, title as fieldTitle, formatNumber, formatCell, columnHeader, columnHeaderUnit, partitionWarnings, formatAnswer, formatWarning, resultLanguage, showCoverage, coverageLabel } from './presentation.js';

import {loadChats, saveChats, chatCopy, newChat} from './chat.js';
import {AnalyticsChart} from './Charts.jsx';
function Answer({result,lang,latest,responseRef}) {
  const effectiveLang=lang,t=copy[lang],execution=result?.execution,data=execution?.result?.outcome?.data,coverage=execution?.result?.coverage;
  const {routine,important}=partitionWarnings(execution?.warnings);
  const title=field=>fieldTitle(field,lang);
  return <section ref={latest?responseRef:null} tabIndex={-1} className={`result-card ${result.status==='answered'?'':'compact'}`} aria-label={t.result}>
        <div className="result-heading"><p className="eyebrow">{t.result}</p><span className={`badge ${result.status==='answered'?'success':''}`}>{t.statuses[result.status]||t.failure}</span></div>
        <h2 className="answer" role={result.status==='error'?'alert':undefined}>{result.error==='network'?t.network:formatAnswer(result,effectiveLang)}</h2>
        {result.status==='answered'&&coverage?.state==='complete'&&<p className="verified">✓ {t.verify}</p>}
        <AnalyticsChart result={result} lang={effectiveLang}/>
        {result.status==='answered'&&data?.rows?.length>0&&<div className="table-wrap"><table><caption>{t.table}</caption><thead><tr>{data.columns.map(c=><th key={c.field}>{columnHeader(c,execution,effectiveLang)}{columnHeaderUnit(c,effectiveLang)&&<small>{columnHeaderUnit(c,effectiveLang)}</small>}</th>)}</tr></thead><tbody>{data.rows.map((row,i)=><tr key={i}>{row.map((v,j)=><td key={j}>{formatCell(v,data.columns[j],effectiveLang)}</td>)}</tr>)}</tbody></table></div>}
        {execution?.truncated&&<p className="notice">{t.truncated}</p>}
        {!!important.length&&<div className="notice"><strong>{t.warnings}</strong><ul>{important.map((w,i)=><li key={i}>{formatWarning(w,effectiveLang)}</li>)}</ul></div>}
        {showCoverage(coverage)&&<section className="evidence"><h3>{t.coverageSummary}</h3><div className="coverage">{coverage.matched_rows!=null&&<div><span>{t.matched}</span><strong>{formatNumber(coverage.matched_rows,effectiveLang)}</strong></div>}{coverage.evaluated_rows!=null&&<div><span>{t.evaluated}</span><strong>{formatNumber(coverage.evaluated_rows,effectiveLang)}</strong></div>}<div><span>{t.coverage}</span><strong>{coverageLabel(coverage.state,effectiveLang)}</strong></div></div>{coverage.issues?.map((v,i)=><p className="notice" key={i}>{t.issues[v.code] || t.issues.other}</p>)}</section>}
        {(execution?.result?.evidence?.length>0||execution?.provenance?.length>0||routine.length>0)&&<details id={latest?"evidence-details":undefined}><summary>{t.evidence}</summary>
          {!!routine.length&&<div className="notice"><strong>{t.warnings}</strong><ul>{routine.map((w,i)=><li key={i}>{formatWarning(w,effectiveLang)}</li>)}</ul></div>}
          {!!execution.result.evidence.length&&<div className="table-wrap"><table><thead><tr><th>{t.source}</th><th>{t.version}</th><th>{t.fields}</th></tr></thead><tbody>{execution.result.evidence.map((e,i)=><tr key={i}><td>{e.source_id}</td><td className="hash">{e.dataset_version}</td><td>{e.logical_fields.map(title).join(', ')}</td></tr>)}</tbody></table></div>}
          {!!execution.provenance?.length&&<><h3>{t.provenance}</h3><div className="table-wrap"><table><thead><tr><th>{t.row}</th><th>{t.source}</th><th>{t.record}</th></tr></thead><tbody>{execution.provenance.map((p,i)=><tr key={i}><td>{p.row}</td><td>{p.source_file}</td><td>{p.source_record}</td></tr>)}</tbody></table></div></>}
          <details><summary>{t.raw}</summary><pre>{JSON.stringify(execution,null,2)}</pre></details>
        </details>}
  </section>;
}
const API = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
function App() {
  const [sessions,setSessions]=useState(()=>loadChats());
  const [active,setActive]=useState(()=>sessions[0]?.id||newChat().id);
  const [lang,setLang]=useState('uz'),[mode,setMode]=useState('auto'),[question,setQuestion]=useState(''),[busy,setBusy]=useState(false),[examples,setExamples]=useState([]),[storageError,setStorageError]=useState(false);
  const pending=useRef(false),controller=useRef(null),responseRef=useRef(null),userRef=useRef(null),follow=useRef(true),programmatic=useRef(false);
  const session=sessions.find(item=>item.id===active),messages=session?.messages||[];
  const latest=[...messages].reverse().find(item=>item.role==='assistant')?.result;
  const effectiveLang=mode==='auto'?resultLanguage(latest,lang):lang,t=copy[effectiveLang],c=chatCopy[effectiveLang];
  useEffect(()=>{document.documentElement.lang=effectiveLang;},[effectiveLang]);
  useEffect(()=>{setStorageError(!saveChats(sessions));},[sessions]);
  useEffect(()=>{let previous=window.scrollY;const track=()=>{if(!programmatic.current){if(window.scrollY<previous-4)follow.current=false;if(document.documentElement.scrollHeight-window.innerHeight-window.scrollY<120)follow.current=true;}previous=window.scrollY;};window.addEventListener('scroll',track,{passive:true});return()=>window.removeEventListener('scroll',track);},[]);
  useEffect(()=>{if(!follow.current)return;const target=busy?userRef.current:responseRef.current;if(target){programmatic.current=true;target.scrollIntoView({block:'start',behavior:'instant'});const frame=requestAnimationFrame(()=>{programmatic.current=false;});return()=>{cancelAnimationFrame(frame);programmatic.current=false;};}},[active,messages.length,busy]);
  useEffect(()=>{const abort=new AbortController();fetch(`${API}/api/examples`,{signal:abort.signal}).then(r=>r.ok?r.json():[]).then(data=>setExamples(Array.isArray(data)?data:[])).catch(()=>{});return()=>{abort.abort();controller.current?.abort();};},[]);
  function append(items,title) {
    setSessions(previous=>{
      const existing=previous.find(item=>item.id===active)||{id:active,title:title||c.newChat,messages:[]};
      return [{...existing,title:existing.messages.length?existing.title:title||existing.title,messages:[...existing.messages,...items].slice(-40)},...previous.filter(item=>item.id!==active)].slice(0,10);
    });
  }
  function createChat(){if(busy)return;follow.current=true;setActive(newChat().id);setQuestion('');}
  async function submit(event){
    event.preventDefault();if(pending.current||!question.trim()||question.length>4000)return;
    const text=question.trim();follow.current=true;pending.current=true;setBusy(true);setQuestion('');append([{role:'user',text}],text.slice(0,70));
    controller.current=new AbortController();const timeout=setTimeout(()=>controller.current.abort(),180000);
    try {
      const response=await fetch(`${API}/api/ask`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:text,language:mode}),signal:controller.current.signal});
      const data=await response.json();
      if(!data?.status||typeof data.answer!=='string')throw Error('invalid response');
      append([{role:'assistant',result:data}]);
    } catch {append([{role:'assistant',result:{language:effectiveLang,status:'error',error:'network',answer:''}}]);}
    finally{clearTimeout(timeout);pending.current=false;setBusy(false);}
  }
  return <div className="chat-shell">
    <aside className="chat-sidebar"><a className="brand" href="/"><span className="mark">U</span><span>UZEX<span className="brand-sub">AI Agent</span></span></a>
      <button className="new-chat" onClick={createChat} disabled={busy}>＋ {c.newChat}</button><p className="eyebrow">{c.history}</p>
      <nav aria-label={c.history}>{sessions.filter(item=>item.messages.length).map(item=><button key={item.id} className={`history-item ${active===item.id?'selected':''}`} disabled={busy} onClick={()=>{follow.current=true;setActive(item.id);setQuestion('');}}>◷ <span>{item.title}</span></button>)}</nav>
      <div className="sidebar-bottom"><p>{c.local}</p><button className="clear-history" disabled={busy||!sessions.length} onClick={()=>{setSessions([]);follow.current=true;setActive(newChat().id);setQuestion('');}}>{c.clear}</button></div>
    </aside>
    <main className="chat-main"><header className="chat-header"><div><strong>{c.workspace}</strong><span className="online-dot">● {c.readonly}</span></div><div className="languages">{['auto','uz','ru'].map(value=><button key={value} aria-pressed={mode===value} disabled={busy} onClick={()=>{setMode(value);if(value!=='auto')setLang(value);}}>{value==='auto'?'Auto':value==='uz'?'O‘zbekcha':'Русский'}</button>)}</div></header>
      <p className="disclaimer">{t.disclaimer}</p>{storageError&&<p className="notice">{c.storageError}</p>}
      <div className="conversation" role="log" aria-label={c.conversation} aria-busy={busy}>
      {!messages.length&&<div className="chat-welcome"><span className="welcome-mark">✳</span><p className="eyebrow">UZEX INTELLIGENCE</p><h1>{t.title}</h1><p>{t.intro}</p><div className="examples">{examples.map(item=><button key={item.id} onClick={()=>{setQuestion(item[effectiveLang]);document.getElementById('question')?.focus();}}>{item[effectiveLang]} <span>↗</span></button>)}</div></div>}
      {messages.map((message,index)=>message.role==='user'?<div className="user-message" ref={index===messages.length-1?userRef:null} key={index}><span>{c.you}</span><p>{message.text}</p></div>:<div className="assistant-message" key={index}><div className="assistant-label"><span className="assistant-icon">U</span> UZEX AI <small>{message.result.status==='answered'?c.verified:t.statuses[message.result.status]||t.failure}</small></div><Answer result={message.result} lang={mode==='auto'?resultLanguage(message.result,effectiveLang):effectiveLang} latest={index===messages.length-1} responseRef={responseRef}/></div>)}
      {busy&&<div className="chat-loading" role="status"><span className="assistant-icon">U</span><span className="loading-dots">● ● ●</span> {t.loading}</div>}
      </div>
      <div className="composer-wrap"><form className="chat-composer" onSubmit={submit}><label className="sr-only" htmlFor="question">{t.label}</label><textarea id="question" rows={2} value={question} onKeyDown={event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.nativeEvent.isComposing){event.preventDefault();if(!event.repeat&&!pending.current&&question.trim())event.currentTarget.form.requestSubmit();}}} onChange={event=>setQuestion(event.target.value)} placeholder={t.placeholder} maxLength={4000} disabled={busy}/><div className="composer-footer"><button className="primary" disabled={busy||!question.trim()}>{busy?'…':t.ask} ↑</button></div></form><p>{c.footer}</p></div>
    </main></div>;
}
createRoot(document.getElementById('root')).render(<App/>);
