import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';
import {resultLanguage, showCoverage, coverageLabel} from './presentation.js';

const API = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const copy = {
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
  deal_count: ['Bitimlar soni','Количество сделок'], deal_value:['Jami summa','Общая сумма'],
  warehouse_region:['Ombor viloyati','Регион склада'], product:['Mahsulot','Товар'],
  status:['Rasmiy holat','Официальный статус'], delivery_completion:['Yetkazib berish','Поставка'],
  currency:['Valyuta','Валюта'], measurement_unit:['O‘lchov birligi','Единица'],
  physical_volume:['Jismoniy hajm','Физический объём'], delivered_lots:['Yetkazilgan lotlar','Поставленные лоты'],
  deal_id:['Bitim raqami','Номер сделки'], deal_date:['Sana','Дата'],
  baseline:['Oldingi davr','Базовый период'], target:['Keyingi davr','Целевой период'],
  absolute_difference:['Farq','Разница'], percentage_change:['O‘zgarish','Изменение'],
};
function cell(value) { return value === null ? '—' : String(value); }
function App() {
  const [lang,setLang] = useState('uz');
  const [languageMode,setLanguageMode] = useState('auto');
  const [question,setQuestion] = useState('');
  const [examples,setExamples] = useState([]);
  const [busy,setBusy] = useState(false);
  const [result,setResult] = useState(null);
  const [error,setError] = useState('');
  const controller = useRef(null);
  const effectiveLang = resultLanguage(result, lang);
  const t = copy[effectiveLang];
  useEffect(() => { document.documentElement.lang = lang; }, [lang]);
  useEffect(() => {
    const abort = new AbortController();
    fetch(`${API}/api/examples`,{signal:abort.signal}).then(r => r.ok ? r.json() : []).then(data => setExamples(Array.isArray(data) ? data : [])).catch(() => {});
    return () => { abort.abort(); controller.current?.abort(); };
  }, []);
  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    if (!question.trim() || question.length > 4000) { setError(t.invalid); return; }
    setBusy(true); setError(''); setResult(null);
    controller.current = new AbortController();
    const timeout = setTimeout(() => controller.current.abort(), 180000);
    try {
      const response = await fetch(`${API}/api/ask`, {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({question:question.trim(),language:languageMode}), signal:controller.current.signal,
      });
      const data = await response.json();
      if (data.status && typeof data.answer === 'string') setResult(data);
      else setError(response.status === 422 ? t.invalid : t.failure);
    } catch { setError(t.network); }
    finally { clearTimeout(timeout); setBusy(false); }
  }
  const execution = result?.execution;
  const data = execution?.result?.outcome?.data;
  const coverage = execution?.result?.coverage;
  const title = field => labels[field]?.[effectiveLang === 'uz' ? 0 : 1] || field;
  return <div className="shell">
    <header><a className="brand" href="/" aria-label="UZEX home"><span className="mark">U</span><span>UZEX<span className="brand-sub">AI Agent</span></span></a><div className="languages" aria-label="Language">{['auto','uz','ru'].map(l=><button key={l} aria-pressed={languageMode===l} onClick={()=>{setLanguageMode(l);if(l!=='auto')setLang(l);setResult(null);}} disabled={busy}>{l==='auto'?'Auto':l==='uz'?'O‘zbekcha':'Русский'}</button>)}</div></header>
    <main><section className="hero"><p className="eyebrow">{t.kicker}</p><h1>{t.title}</h1><p className="intro">{t.intro}</p></section>
    <div className="workspace"><section className="question-card"><form onSubmit={submit}><label htmlFor="question">{t.label}</label><textarea id="question" value={question} onChange={e=>setQuestion(e.target.value)} maxLength={4000} placeholder={t.placeholder} disabled={busy} rows={5} required/><div className="input-footer"><span>{question.length}/4000</span><button className="primary" type="submit" disabled={busy||!question.trim()}>{busy?'…':t.ask}<span aria-hidden="true"> ↗</span></button></div><p className="hint">{t.hint}</p></form><div className="examples"><h2>{t.examples}</h2>{examples.map(e=><button key={e.id} onClick={()=>{setQuestion(e[lang]);document.getElementById('question')?.focus();}} disabled={busy}>{e[lang]}<span aria-hidden="true">↗</span></button>)}</div></section>
    <section className="result-card" aria-live="polite" aria-busy={busy}>
      {busy?<div className="empty"><span className="empty-symbol">···</span><h2>{t.loading}</h2></div>:error?<div role="alert" className="notice error">{error}</div>:!result?<div className="empty"><span className="empty-symbol">↗</span><h2>{t.empty}</h2><p>{t.emptyBody}</p></div>:<>
        <div className="result-heading"><p className="eyebrow">{t.result}</p><span className={`badge ${result.status==='answered'?'success':''}`}>{t.statuses[result.status]||result.status}</span></div>
        <h2 className="answer">{result.answer}</h2>
        {result.error&&<p role="alert" className="notice error">{t.errors[result.error]||t.failure} <code>{result.error}</code></p>}
        {result.status==='answered'&&<p className="verified">✓ {t.verify}</p>}
        {data&&<div className="table-wrap"><table><caption>{t.table}</caption><thead><tr>{data.columns.map(c=><th key={c.field}>{title(c.field)}{(c.currency||c.unit)&&<small>{[c.currency,c.unit].filter(Boolean).join(' / ')}</small>}</th>)}</tr></thead><tbody>{data.rows.map((row,i)=><tr key={i}>{row.map((v,j)=><td key={j}>{cell(v)}</td>)}</tr>)}</tbody></table></div>}
        {execution?.truncated&&<p className="notice">{t.truncated}</p>}
        {!!execution?.warnings?.length&&<div className="notice"><strong>{t.warnings}</strong><ul>{execution.warnings.map((w,i)=><li key={i}>{w}</li>)}</ul></div>}
        {showCoverage(coverage)&&<details className="evidence"><summary>{t.evidence}</summary><div className="coverage"><div><span>{t.matched}</span><strong>{cell(coverage.matched_rows)}</strong></div><div><span>{t.evaluated}</span><strong>{cell(coverage.evaluated_rows)}</strong></div><div><span>{t.coverage}</span><strong>{coverageLabel(coverage.state, effectiveLang)}</strong></div></div>{coverage.issues?.map((v,i)=><p className="notice" key={i}>{v.description}</p>)}{!!execution.result.evidence.length&&<div className="table-wrap"><table><thead><tr><th>{t.source}</th><th>{t.version}</th><th>{t.fields}</th></tr></thead><tbody>{execution.result.evidence.map((e,i)=><tr key={i}><td>{e.source_id}</td><td className="hash">{e.dataset_version}</td><td>{e.logical_fields.map(title).join(', ')}</td></tr>)}</tbody></table></div>}</details>}
        {!!execution?.provenance?.length&&<details><summary>{t.provenance}</summary><div className="table-wrap"><table><thead><tr><th>{effectiveLang==='uz'?'Qator':'Строка'}</th><th>{t.source}</th><th>{effectiveLang==='uz'?'Yozuv':'Запись'}</th></tr></thead><tbody>{execution.provenance.map((p,i)=><tr key={i}><td>{p.row}</td><td>{p.source_file}</td><td>{p.source_record}</td></tr>)}</tbody></table></div></details>}
        {!!execution?.periods?.length&&<details><summary>{t.period}</summary><pre>{JSON.stringify(execution.periods,null,2)}</pre></details>}
        {execution?.scope&&<details><summary>{t.scope}</summary><pre>{JSON.stringify(execution.scope,null,2)}</pre></details>}
      </>}
    </section></div></main><footer><span>UZEX AI Agent</span><span>{effectiveLang==='uz'?'Sun’iy ma’lumotlar · Jonli UZEX ma’lumotlari emas':'Синтетические данные · Не реальные данные UZEX'}</span></footer>
  </div>;
}
createRoot(document.getElementById('root')).render(<App/>);
