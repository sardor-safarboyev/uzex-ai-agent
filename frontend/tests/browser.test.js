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
const payload={language:'uz',status:'answered',answer:'',execution:{returned_rows:1,warnings:[],provenance:[{row:1,source_file:'deals_2024.csv',source_record:123}],scope:{request:{kind:'aggregate',metrics:['deal_count']}},result:{coverage:{state:'complete',matched_rows:500000,evaluated_rows:500000,issues:[]},evidence:[{source_id:'deals_2024.csv',dataset_version:'abc',logical_fields:['deal_count'],mapping_verified:true}],outcome:{status:'answered',data:{columns:[{field:'deal_count',unit:'transactions'}],rows:[[500000]]}}}}};
let calls=0;window.fetch=async url=>{if(String(url).endsWith('/api/ask'))calls++;return new Response(JSON.stringify(String(url).endsWith('/api/examples')?[{id:'count',uz:'Bitimlar soni qancha?',ru:'Сколько всего сделок?'}]:payload),{status:200});};
localStorage.removeItem('uzex.chats.v1');
await import('/src/main.jsx');
const delay=()=>new Promise(resolve=>setTimeout(resolve,20));
async function wait(check){for(let i=0;i<150;i++){if(check())return;await delay();}throw Error('UI timeout');}
function check(value,message){if(!value)throw Error(message);}
try{
 await wait(()=>document.querySelector('.examples button'));
 check(document.querySelector('.disclaimer').textContent.includes('sintetik'),'Disclaimer retained');
 document.querySelector('.examples button').click();await delay();
 const input=document.querySelector('textarea');
 const shifted=new KeyboardEvent('keydown',{key:'Enter',shiftKey:true,bubbles:true,cancelable:true});input.dispatchEvent(shifted);
 check(!shifted.defaultPrevented&&calls===0,'Shift Enter preserves newline behavior');
 input.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true}));
 input.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true}));
 await wait(()=>document.querySelector('.assistant-message'));
 check(document.querySelector('.user-message').textContent.includes('Bitimlar'),'User question rendered');check(calls===1,'Enter uses the guarded submit path');check(!document.querySelector('.composer-footer').textContent.includes('mustaqil'),'No redundant footer text');
 check(document.querySelector('.answer').textContent.includes('500 000'),'Verified result retained');
 check(document.querySelector('table'),'Answer table retained');
 const evidence=document.querySelector('details');evidence.open=true;
 check(evidence.textContent.includes('deals_2024.csv'),'Provenance retained');
 await delay();check(JSON.parse(localStorage.getItem('uzex.chats.v1')).length===1,'Session persisted');
 document.querySelector('.new-chat').click();await wait(()=>document.querySelector('.chat-welcome'));
 check(!document.querySelector('.assistant-message'),'New chat is empty');
 document.querySelector('.history-item').click();await wait(()=>document.querySelector('.assistant-message'));
 check(document.querySelector('.answer').textContent.includes('500 000'),'History restores answer');
 [...document.querySelectorAll('.languages button')].find(button=>button.textContent==='Русский').click();await delay();
 check(document.querySelector('.answer').textContent.includes('Всего'),'Bilingual answer retained');
 check(document.documentElement.scrollWidth<=window.innerWidth+1,'Responsive without page overflow');
 document.querySelector('.clear-history').click();await wait(()=>document.querySelector('.chat-welcome'));
 await delay();check(JSON.parse(localStorage.getItem('uzex.chats.v1')).length===0,'History cleared');
 document.getElementById('test-status').textContent='passed';
}catch(error){document.getElementById('test-status').textContent='failed: '+error.stack;}
</script></body></html>`;

for (const [name,width,height] of [['mobile narrow',320,740],['mobile',390,844],['laptop',1366,900]]) {
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
        await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:name.startsWith('mobile')});
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
