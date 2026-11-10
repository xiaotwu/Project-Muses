// MIT. Minimal, explicitly scoped host interfaces for the P0 GET/JSON POST probes.
import { ReadableStream, WritableStream, TransformStream } from 'web-streams-polyfill';
Object.assign(globalThis, { ReadableStream, WritableStream, TransformStream });
globalThis.console = { log() {}, info() {}, warn() {}, error() {}, debug() {} };
globalThis.TextEncoder = class { encode(s = '') { return new Uint8Array(nativeEncode(String(s))); } };
globalThis.TextDecoder = class { decode(b = new Uint8Array()) { return nativeDecode(b); } };
globalThis.btoa = s => nativeBase64(s, false);
globalThis.atob = s => nativeBase64(s, true);
globalThis.structuredClone = value => JSON.parse(JSON.stringify(value));
const escape = s => encodeURIComponent(String(s)).replace(/%20/g, '+').replace(/[!'()~]/g, c => '%' + c.charCodeAt(0).toString(16).toUpperCase());
const unescape = s => decodeURIComponent(s.replace(/\+/g, ' '));
globalThis.URLSearchParams = class {
  constructor(value = '', changed) { this.changed = changed; this.values = typeof value === 'string' ? value.replace(/^\?/, '').split('&').filter(Boolean).map(p => { const i = p.indexOf('='); return i < 0 ? [unescape(p), ''] : [unescape(p.slice(0, i)), unescape(p.slice(i + 1))]; }) : Array.isArray(value) || value[Symbol.iterator] ? [...value].map(([k,v]) => [String(k), String(v)]) : Object.entries(value).map(([k,v])=>[k,String(v)]); }
  get(k) { return this.values.find(p=>p[0]===k)?.[1] ?? null; }
  getAll(k) { return this.values.filter(p=>p[0]===k).map(p=>p[1]); }
  has(k) { return this.values.some(p=>p[0]===k); }
  set(k,v) { const i=this.values.findIndex(p=>p[0]===k); this.values=this.values.filter((p,n)=>p[0]!==k||n===i); if(i<0)this.values.push([String(k),String(v)]);else this.values[i]=[String(k),String(v)];this.changed?.(this.toString()); }
  append(k,v) {this.values.push([String(k),String(v)]);this.changed?.(this.toString());}
  delete(k) {this.values=this.values.filter(p=>p[0]!==k);this.changed?.(this.toString());}
  toString(){return this.values.map(([k,v])=>escape(k)+'='+escape(v)).join('&');}
  entries(){return this.values[Symbol.iterator]();}keys(){return this.values.map(p=>p[0])[Symbol.iterator]();}forEach(f){for(const[k,v]of this.values)f(v,k,this);}[Symbol.iterator](){return this.entries();}
};
globalThis.URL = class {
  constructor(input,base=''){this.p=JSON.parse(nativeURL(String(input),String(base)));this._params();}
  _params(){this.searchParams=new URLSearchParams(this.p.search,s=>{this.p=JSON.parse(nativeURL(this.p.href,'','search',s));});}
  toString(){return this.p.href;}toJSON(){return this.p.href;}
};
for(const key of ['href','protocol','host','hostname','port','pathname','search','hash','origin']) Object.defineProperty(URL.prototype,key,{get(){return this.p[key];},set(v){this.p=JSON.parse(key==='href'?nativeURL(String(v),''):nativeURL(this.p.href,'',key,String(v)));this._params();}});
globalThis.Headers = class {
  constructor(init={}){this.map=new Map();for(const[k,v]of init[Symbol.iterator]?init:Object.entries(init))this.set(k,v);}
  set(k,v){this.map.set(String(k).toLowerCase(),String(v));}get(k){return this.map.get(String(k).toLowerCase())??null;}has(k){return this.map.has(String(k).toLowerCase());}delete(k){this.map.delete(String(k).toLowerCase());}append(k,v){this.set(k,this.has(k)?this.get(k)+', '+v:v);}entries(){return this.map.entries();}[Symbol.iterator](){return this.entries();}forEach(f){this.map.forEach((v,k)=>f(v,k,this));}
};
globalThis.Event = class {constructor(type){this.type=type;}};
globalThis.CustomEvent = class extends Event {constructor(type,init={}){super(type);this.detail=init.detail;}};
globalThis.EventTarget = class {constructor(){this.listeners=new Map();}addEventListener(type,fn){if(!this.listeners.has(type))this.listeners.set(type,new Set());this.listeners.get(type).add(fn);}removeEventListener(type,fn){this.listeners.get(type)?.delete(fn);}dispatchEvent(e){for(const fn of this.listeners.get(e.type)||[])fn(e);return true;}};
globalThis.DOMException = class extends Error {constructor(message,name='Error'){super(message);this.name=name;}};
globalThis.AbortSignal = class extends EventTarget {constructor(){super();this.aborted=false;}throwIfAborted(){if(this.aborted)throw this.reason;}static timeout(ms){const c=new AbortController();setTimeout(()=>c.abort(new DOMException('timeout','TimeoutError')),ms);return c.signal;}};
globalThis.AbortController = class {constructor(){this.signal=new AbortSignal();}abort(reason=new DOMException('aborted','AbortError')){if(this.signal.aborted)return;this.signal.aborted=true;this.signal.reason=reason;this.signal.dispatchEvent(new Event('abort'));}};
globalThis.Request = class {constructor(input,init={}){this.url=String(input instanceof Request?input.url:input);this.method=init.method||input.method||'GET';this.headers=new Headers(init.headers||input.headers);this.body=init.body??input.body;this.signal=init.signal||input.signal;this.redirect=init.redirect||input.redirect||'follow';}};
globalThis.Response = class {constructor(body=new ArrayBuffer(0),init={}){Object.assign(this,init);this.status=init.status??200;this.statusText='';this.ok=this.status>=200&&this.status<300;this.headers=new Headers(init.headers);this.data=typeof body==='string'?nativeEncode(body):body;this.body=new ReadableStream({start:c=>{c.enqueue(new Uint8Array(this.data));c.close();}});}async text(){return nativeDecode(this.data);}async json(){return JSON.parse(await this.text());}async arrayBuffer(){return this.data;}clone(){return new Response(this.data,{status:this.status,headers:this.headers,url:this.url});}};
globalThis.FormData = class {constructor(){throw new Error('FormData unavailable in P0 scope');}};
globalThis.File = class {constructor(){throw new Error('File unavailable in P0 scope');}};
const pending=new Map();let requestID=0;
globalThis.fetch=(input,init={})=>new Promise((resolve,reject)=>{const r=new Request(input,{...(input instanceof Request?input:{}),...init});r.signal?.throwIfAborted();const id=++requestID;const abort=()=>{nativeCancel(id);pending.delete(id);reject(r.signal.reason);};const cleanup=()=>r.signal?.removeEventListener('abort',abort);pending.set(id,{resolve,reject,cleanup});r.signal?.addEventListener('abort',abort);try{nativeRequest(JSON.stringify({id,url:r.url,method:r.method,headers:Object.fromEntries(r.headers),body:r.body}));}catch(e){pending.delete(id);cleanup();reject(e);}});
globalThis.nativeDeliver=(id,json,body)=>{const p=pending.get(id);if(!p)return;pending.delete(id);p.cleanup();const meta=JSON.parse(json);if(meta.error){p.reject(new DOMException(meta.error,meta.error==='aborted'?'AbortError':meta.error==='timeout'?'TimeoutError':'NetworkError'));return;}p.resolve(new Response(body,meta));};
let timerID=0;const timers=new Map();globalThis.setTimeout=(fn,ms=0,...args)=>{const id=++timerID;timers.set(id,()=>fn(...args));nativeTimer(id,ms);return id;};globalThis.clearTimeout=id=>{timers.delete(id);nativeTimer(id,-1);};globalThis.nativeTimerDeliver=id=>{const fn=timers.get(id);timers.delete(id);fn?.();};
globalThis.performance={now:()=>Date.now()};
globalThis.crypto={randomUUID:()=>nativeUUID()};
