// SPDX-License-Identifier: MIT
// Actual P0 JS fetch/stream shims; native callbacks below are deterministic mocks.
import '../../source/shims.js';
const bytes = text => Uint8Array.from([...text].map(c => c.charCodeAt(0))).buffer;
globalThis.nativeEncode = bytes;
globalThis.nativeDecode = buffer => String.fromCharCode(...new Uint8Array(buffer));
let requests = 0, cancellations = 0;
globalThis.nativeCancel = () => { cancellations++; };
globalThis.nativeTimer = () => {};
globalThis.nativeRequest = encoded => {
  const request = JSON.parse(encoded);requests++;
  if (request.url === 'https://fixture.invalid/pending') return;
  if (request.method !== 'POST' || request.body !== '{"fixture":1}' || request.headers['content-type'] !== 'application/json') throw Error('request fixture mismatch');
  Promise.resolve().then(() => nativeDeliver(request.id, JSON.stringify({status:200,headers:{'content-type':'application/json'},url:request.url}), bytes('{"ok":true}')));
};
globalThis.smokeDone = false;
(async () => {
  const result = await fetch('https://fixture.invalid/metadata', {method:'POST',headers:{'Content-Type':'application/json'},body:'{"fixture":1}'});
  const copy = result.clone();
  if (!(await result.json()).ok || nativeDecode(await copy.arrayBuffer()) !== '{"ok":true}') throw Error('response fixture mismatch');
  const controller = new AbortController();
  const pending = fetch('https://fixture.invalid/pending', {signal:controller.signal});
  controller.abort();
  let aborted = false;try { await pending; } catch(error) { aborted = error.name === 'AbortError'; }
  const collected = [];
  const reader = new ReadableStream({start(c){c.enqueue(new Uint8Array([1,2]));c.close();}}).getReader();
  while(true){const {done,value}=await reader.read();if(done)break;collected.push(...value);}
  if (!aborted || cancellations !== 1 || requests !== 2 || collected.join(',') !== '1,2') throw Error('lifecycle fixture mismatch');
  globalThis.smokeDone = true;
})();
