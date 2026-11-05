import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync, spawn } from 'node:child_process';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';

const chrome = process.env.CHROME_BIN || 'google-chrome';
const available = spawnSync(chrome,['--version'],{encoding:'utf8'}).status === 0;
const harness = String.raw`<!doctype html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><output id="test-status">pending</output><script type="module">
window.addEventListener('error',event=>document.getElementById('test-status').textContent='failed: '+event.message);
window.addEventListener('unhandledrejection',event=>document.getElementById('test-status').textContent='failed: '+event.reason?.message);
const initial={language:'uz',status:'answered',answer:'Bitimlar soni: 500000 transactions',error:null,execution:{returned_rows:1,effective_limit:100,truncated:false,warnings:['Source NULL values were retained and were not imputed.'],provenance:[{row:1,source_file:'deals_2024.csv',source_record:123}],periods:[],scope:{language:'uz',request:{kind:'aggregate',metrics:['deal_count']}},result:{coverage:{state:'complete',matched_rows:500000,evaluated_rows:500000,issues:[]},evidence:[{source_id:'deals_2024.csv',dataset_version:'a'.repeat(256),logical_fields:['deal_count'],mapping_verified:true}],outcome:{status:'answered',data:{columns:[{field:'deal_count',unit:'transactions'}],rows:[[500000]]}}}}};
let payload=initial, calls=0, release=null;
const original=JSON.stringify(initial);
window.fetch=async (url,options={})=>{
 if(String(url).endsWith('/api/examples')) return new Response(JSON.stringify([{id:'count',uz:'Bitimlar soni?',ru:'Сколько сделок?'}]),{status:200});
 if(String(url).endsWith('/api/ask')) {calls++; const snapshot=structuredClone(payload);if(release===true)await new Promise(resolve=>release=resolve);return new Response(JSON.stringify(snapshot),{status:snapshot.error?503:200});}
 throw new Error('Unexpected network request');
};
await import('/src/main.jsx');
const delay=()=>new Promise(resolve=>setTimeout(resolve,20));
async function waitFor(check){for(let i=0;i<150;i++){if(check())return;await delay();}throw Error('Timed out waiting for UI');}
function check(value,message){if(!value)throw Error(message);}
function language(value){document.querySelectorAll('.languages button')[value==='uz'?0:1].click();}
async function ask(){document.querySelector('.examples button').click();await delay();document.querySelector('form').requestSubmit();await delay();await waitFor(()=>document.querySelector('.answer')&&document.querySelector('.result-card').getAttribute('aria-busy')==='false');}
try {
 await waitFor(()=>document.querySelector('.examples button'));
 check(document.querySelector('.disclaimer').textContent.includes('sintetik'),'Uzbek disclaimer');
 await ask();
 check(document.querySelector('.answer').textContent==='Jami 500 000 ta bitim qayd etilgan.','Natural Uzbek answer');
 check(document.activeElement===document.querySelector('.result-card'),'Result receives focus');
 check(document.querySelector('.result-card').getBoundingClientRect().top>=0,'Result scrolled into view');
 check(document.querySelector('tbody td').textContent==='500 000','Grouped result cell');
 const evidence=document.getElementById('evidence-details');
 check(!evidence.open,'Evidence initially collapsed');
 evidence.querySelector('summary').click();await delay();check(evidence.open,'Evidence expands');
 check(evidence.textContent.includes('a'.repeat(256)),'Exact hash accessible');
 check(evidence.textContent.includes('deals_2024.csv'),'Filename accessible');
 check(evidence.textContent.includes('123'),'Record provenance accessible');
 evidence.querySelector('summary').click();await delay();check(!evidence.open,'Evidence collapses');
 language('ru');await delay();
 check(document.documentElement.lang==='ru','Page language changes');
 check(document.querySelector('.answer').textContent==='Всего зарегистрировано 500 000 сделок.','Answer toggles without API request');
 check(calls===1,'Toggle avoids another request');
 check(document.querySelector('.disclaimer').textContent.includes('Синтетические данные'),'Russian disclaimer');
 check(evidence.querySelector('summary').textContent==='Источники и проверка','Evidence label toggles');
 check(document.querySelector('.notice').textContent.includes('Пустые значения'),'Warning toggles');
 check(!document.querySelector('.coverage').textContent.includes('complete'),'Coverage state localized');
 check(JSON.stringify(initial)===original,'Original numbers and metadata unchanged');
 payload={...initial,status:'insufficient_data',execution:{...initial.execution,result:{...initial.execution.result,coverage:{state:'partial',matched_rows:10,evaluated_rows:20,issues:[{code:'missing_values',description:'Original missing values warning'}]},outcome:{status:'insufficient_data',explanation:'Original explanation'}}}};
 await ask();
 check(document.querySelector('.coverage').textContent.includes('Частичный'),'Partial coverage accurate');
 check(!document.querySelector('.verified'),'Partial coverage has no verified badge');
 check(!document.querySelector('.coverage').textContent.includes('Полный'),'No false complete coverage');
 payload={...initial,status:'unsupported',execution:null};await ask();
 check(document.querySelector('.answer').textContent.includes('не поддерживается'),'Unsupported state preserved');
 language('uz');await delay();check(document.querySelector('.answer').textContent.includes('qo‘llanmaydi'),'Unsupported toggles');
 payload={...initial,status:'ambiguous',execution:null};await ask();
 check(document.querySelector('.answer').textContent.includes('aniqlashtiring'),'Clarification preserved');
 payload={...initial,status:'error',error:'rate_limit',execution:null};await ask();
 check(document.querySelector('[role=alert]').textContent.includes('Xizmat band'),'Rate limit preserved');
 language('ru');await delay();check(document.querySelector('[role=alert]').textContent.includes('Сервис занят'),'Rate limit toggles');
 payload={...initial,status:'error',error:'provider_error',execution:null};await ask();
 check(document.querySelector('[role=alert]').textContent.includes('Языковой сервис недоступен'),'Provider error preserved');
 payload=initial;release=true;
 document.querySelector('.examples button').click();await delay();
 const form=document.querySelector('form'), before=calls;
 form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));
 await waitFor(()=>typeof release==='function'&&document.querySelector('.empty')&&document.querySelector('.primary').disabled);
 check(calls===before+1,'Duplicate submissions blocked');
 check(document.querySelector('.primary').disabled,'Pending submit disabled');
 check(document.querySelector('.empty').textContent.includes('Проверяем запрос'),'Localized loading');
 release();await waitFor(()=>document.querySelector('.answer'));
 evidence.open=true;await delay();
 check(document.documentElement.scrollWidth<=window.innerWidth+1,'No horizontal page overflow');
 document.getElementById('test-status').textContent='passed';
} catch(error){document.getElementById('test-status').textContent='failed: '+error.stack;}
</script></body></html>`;

for (const [name,width,height] of [['mobile',390,844],['laptop',1366,900]]) {
  test(`mocked UI in Chrome: ${name}`, {skip:!available,timeout:45000}, async () => {
    const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,plugins:[{name:'mocked-presentation-tests',configureServer(server){server.middlewares.use('/__presentation_test',(_req,res)=>{res.setHeader('Content-Type','text/html');res.end(harness);});}}],server:{host:'127.0.0.1',port:0},logLevel:'silent'});
    const profile=await mkdtemp(join(tmpdir(),'uzex-presentation-'));
    try {
      await server.listen();
      const port=server.httpServer.address().port;
      // CDP waits on actual UI completion; virtual time can outrun Vite transforms.
      const child=spawn(chrome,['--headless','--no-sandbox','--disable-gpu','--disable-dev-shm-usage','--no-proxy-server',`--user-data-dir=${profile}`,'--remote-debugging-port=0','about:blank']);
      let socket;
      try {
        const debugPort=await new Promise((resolve,reject)=>{
          let stderr='';
          child.stderr.on('data',data=>{
            stderr+=data;
            const match=stderr.match(/DevTools listening on ws:\/\/127\.0\.0\.1:(\d+)/);
            if(match)resolve(Number(match[1]));
          });
          child.on('error',reject);
          child.on('exit',code=>reject(Error(`Chrome exited ${code}`)));
        });
        const pages=await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json();
        socket=new WebSocket(pages.find(page=>page.type==='page').webSocketDebuggerUrl);
        await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
        const callbacks=new Map();let id=0;
        socket.addEventListener('message',event=>{
          const message=JSON.parse(event.data);
          if(message.id&&callbacks.has(message.id)){callbacks.get(message.id)(message);callbacks.delete(message.id);}
        });
        const send=(method,params={})=>new Promise(resolve=>{const key=++id;callbacks.set(key,resolve);socket.send(JSON.stringify({id:key,method,params}));});
        await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:name==='mobile'});
        await send('Page.navigate',{url:`http://127.0.0.1:${port}/__presentation_test`});
        let status;
        for(let i=0;i<200;i++){
          const reply=await send('Runtime.evaluate',{expression:"document.getElementById('test-status')?.textContent",returnByValue:true});
          status=reply.result?.result?.value;
          if(status&&status!=='pending')break;
          await delay(100);
        }
        assert.equal(status,'passed',status || 'Browser test did not complete');
      } finally {
        socket?.close();
        child.kill('SIGTERM');
        await new Promise(resolve=>child.once('close',resolve));
      }
    } finally {await server.close();await rm(profile,{recursive:true,force:true});}
  });
}
