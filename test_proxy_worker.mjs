import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
const source=await readFile(new URL('./proxy-worker.js',import.meta.url),'utf8');
const {default:worker}=await import(`data:text/javascript,${encodeURIComponent(source)}`);
const env={PROXY_TOKEN:'test-only-token',SEC_CONTACT_EMAIL:'test@example.com'};

test('proxy fails closed without configuration or matching token',async()=>{
 assert.equal((await worker.fetch(new Request('https://worker.test/submissions/x'),{})).status,503);
 assert.equal((await worker.fetch(new Request('https://worker.test/submissions/x'),env)).status,401);
});

test('both SEC archive path cases route to the canonical SEC Archives path',async()=>{
 const old=globalThis.fetch;
 const targets=[];
 globalThis.fetch=async(url,options)=>{targets.push({url,options});return new Response('official document',{status:200});};
 try {
  for(const path of ['archives','Archives']) {
   const request=new Request(`https://worker.test/${path}/edgar/data/1/release.htm`,{headers:{'X-Proxy-Token':'test-only-token'}});
   assert.equal((await worker.fetch(request,env)).status,200);
  }
  assert.equal(targets.length,2);
  assert.ok(targets.every(t=>t.url==='https://www.sec.gov/Archives/edgar/data/1/release.htm'));
  assert.ok(targets.every(t=>t.options.headers['User-Agent']==='EarningsTracker test@example.com'));
 } finally {globalThis.fetch=old;}
});

test('proxy does not become a general-purpose relay',async()=>{
 const request=new Request('https://worker.test/unsupported/https://example.com',{headers:{'X-Proxy-Token':'test-only-token'}});
 assert.equal((await worker.fetch(request,env)).status,403);
});
