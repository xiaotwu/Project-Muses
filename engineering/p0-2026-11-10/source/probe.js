// MIT. Public, unauthenticated probes; output intentionally contains no content or stream URLs.
import './shims.js';
import { Innertube, Platform, Log, Constants } from 'youtubei.js/web';
const emit=(gate,outcome,extra={})=>nativePrint(JSON.stringify({gate,outcome,...extra}));
const error=e=>({error_name:e?.name||'Error',error_category:/^network_[-\d]+$|^response_limit$|^No valid URL to decipher$|^isolated player evaluation failed$|not a function|is not defined|stack overflow|out of memory|interrupted/.test(e?.message||'')?String(e.message).replace(/https?:\/\/\S+/g,'[url]').slice(0,140):/sign in|bot|LOGIN_REQUIRED/i.test(e?.message||'')?'provider_auth_or_challenge':/unavailable|unplayable/i.test(e?.message||'')?'provider_unavailable':'redacted'});
Log.setLevel(Log.Level.NONE);
Platform.load({runtime:'muses-quickjs-p0',server:true,Cache:class {async get(){}async set(){}async remove(){}},sha1Hash:async s=>nativeSHA1(s),uuidv4:()=>nativeUUID(),eval:(data,env)=>JSON.parse(nativeEval(data.output)),fetch,Headers,Request,Response,FormData,File,ReadableStream,CustomEvent});
async function main(){
 emit('host_capabilities','pass',{runtime:globalThis.PROBE_RUNTIME||'QuickJS 2026-06-04',library:'youtubei.js 18.3.0',native_network:'URLSession',webview:false,node_runtime:false});
 if(PROBE_MODE==='interrupt'){emit('interrupt_started','pass');for(;;){} }
 if(PROBE_MODE==='memory'){try{let allocations=[];for(;;)allocations.push(new Uint8Array(8*1024*1024));}catch(e){emit('memory_limit',/out of memory/.test(e.message)?'pass':'fail',error(e));nativeFinish(0);}return;}
 if(PROBE_MODE==='sandbox'){const capabilities=JSON.parse(nativeEval('return {network:typeof fetch,native:typeof nativeRequest,process:typeof process};'));emit('player_sandbox',Object.values(capabilities).every(v=>v==='undefined')?'pass':'fail');let t=Date.now();try{nativeEval('for(;;){}');emit('player_timeout','fail');}catch(e){emit('player_timeout','pass',{elapsed_ms:Date.now()-t});}nativeFinish(0);return;}
 if(PROBE_MODE==='cancel'){
   const controller=new AbortController();let start=Date.now();const request=fetch('https://www.youtube.com/iframe_api',{signal:controller.signal});controller.abort();try{await request;emit('native_cancellation','fail');nativeFinish(1);}catch(e){emit('native_cancellation',e.name==='AbortError'?'pass':'fail',{elapsed_ms:Date.now()-start,...error(e)});nativeFinish(e.name==='AbortError'?0:1);}return;
 }
 let started=Date.now();let yt;
 try{yt=await Innertube.create({retrieve_player:PROBE_MODE==='media'||PROBE_MODE.startsWith('player_'),generate_session_locally:true,enable_session_cache:false,timezone:'America/Los_Angeles',lang:'en',location:'US',fetch});emit('session','pass',{elapsed_ms:Date.now()-started,player_loaded:!!yt.session.player});}catch(e){emit('session','fail',{elapsed_ms:Date.now()-started,...error(e)});nativeFinish(1);return;}
 if(PROBE_MODE==='catalog'){
   let ok=true;
   started=Date.now();try{const result=await yt.search('Big Buck Bunny',{type:'video'});if(!result.videos.length)ok=false;emit('search',result.videos.length?'pass':'fail',{elapsed_ms:Date.now()-started,result_count:result.results.length,video_count:result.videos.length,has_continuation:result.has_continuation});if(result.has_continuation){started=Date.now();const next=await result.getContinuation();if(!next.results.length)ok=false;emit('search_continuation',next.results.length?'pass':'fail',{elapsed_ms:Date.now()-started,result_count:next.results.length});}}catch(e){ok=false;emit('search','fail',{elapsed_ms:Date.now()-started,...error(e)});}
   started=Date.now();try{const result=await yt.music.search('Blender');if(!result.contents?.length)ok=false;emit('music_search',result.contents?.length?'pass':'fail',{elapsed_ms:Date.now()-started,section_count:result.contents?.length||0});}catch(e){ok=false;emit('music_search','fail',{elapsed_ms:Date.now()-started,...error(e)});}
   nativeFinish(ok?0:1);return;
 }
 started=Date.now();try{
   const direct=PROBE_MODE!=='media',full=PROBE_MODE.startsWith('background_')||PROBE_MODE.startsWith('player_');
   const info=await yt.getBasicInfo(PROBE_MODE.endsWith('next')?'eRsGyueVLvQ':'aqz-KE-bpKQ',direct?{client:'IOS'}:undefined);const formats=info.streaming_data?.adaptive_formats||[];
   emit('media_metadata','pass',{elapsed_ms:Date.now()-started,status:info.playability_status?.status||'unknown',format_count:formats.length,audio_format_count:formats.filter(f=>f.has_audio&&!f.has_video).length,url_format_count:formats.filter(f=>!!f.url).length,cipher_format_count:formats.filter(f=>!!f.signature_cipher||!!f.cipher).length,has_hls:!!info.streaming_data?.hls_manifest_url,has_sabr:!!info.streaming_data?.server_abr_streaming_url});
   if(PROBE_MODE==='hls_probe'){
     let manifest=info.streaming_data?.hls_manifest_url;if(!manifest){emit('hls_manifest','fail',{reason:'not_provided'});nativeFinish(1);return;}
     for(let level=0;level<3;level++){
       const r=await fetch(manifest,{signal:AbortSignal.timeout(15000)});const text=await r.text();emit('hls_manifest',r.ok?'pass':'fail',{level,http_status:r.status,bytes:text.length,encrypted:/#EXT-X-KEY:/.test(text)});if(!r.ok||/#EXT-X-KEY:/.test(text)){nativeFinish(1);return;}
       const lines=text.split(/\r?\n/).filter(s=>s&&s[0]!=='#');const audio=text.split(/\r?\n/).find(s=>s.startsWith('#EXT-X-MEDIA:')&&s.includes('TYPE=AUDIO'))?.match(/URI="([^"]+)"/)?.[1];
       if(text.includes('#EXT-X-STREAM-INF:')||audio){manifest=new URL(audio||lines[0],manifest).href;continue;}
       let success=0;for(let i=0;i<Math.min(3,lines.length);i++){started=Date.now();const segment=await fetch(new URL(lines[i],manifest),{signal:AbortSignal.timeout(15000)});const bytes=await segment.arrayBuffer();emit('hls_segment',segment.ok&&bytes.byteLength>0?'pass':'fail',{segment:i,http_status:segment.status,bytes:bytes.byteLength,elapsed_ms:Date.now()-started});if(segment.ok&&bytes.byteLength)success++;}
       nativeFinish(success===Math.min(3,lines.length)&&success>0?0:1);return;
     }emit('hls_manifest','fail',{reason:'nesting_limit'});nativeFinish(1);return;
   }
   const format=info.chooseFormat({type:'audio',quality:'best'});started=Date.now();const url=await format.decipher(yt.session.player);
   emit('media_resolution','pass',{elapsed_ms:Date.now()-started,itag:format.itag,mime_type:format.mime_type?.split(';')[0]||'unknown'});
   if(PROBE_MODE==='range_probe'){for(const [start,end] of [[0,65535],[65536,131071],[0,262143],[0,1048575]]){started=Date.now();const r=await fetch(url,{headers:{Range:`bytes=${start}-${end}`},signal:AbortSignal.timeout(10000)});const b=await r.arrayBuffer();emit('range_probe',r.ok?'pass':'fail',{range_start:start,range_end:end,http_status:r.status,bytes:b.byteLength,elapsed_ms:Date.now()-started});}nativeFinish(0);return;}
   if(full){
     const length=Number(format.content_length);if(!Number.isSafeInteger(length)||length<1||length>16777216)throw new RangeError('total media limit');
     started=Date.now();let stored=0,chunks=0;
     // Match upstream FormatUtils.download: range query + cpn + STREAM_HEADERS.
     for(let offset=0;offset<length;offset+=1048576){const end=Math.min(length-1,offset+1048575);const response=await fetch(`${url}&cpn=${info.cpn}&range=${offset}-${end}`,{headers:Constants.STREAM_HEADERS,signal:AbortSignal.timeout(15000)});const body=await response.arrayBuffer();if(!response.ok||body.byteLength!==end-offset+1){emit('media_bounded_download','fail',{http_status:response.status,bytes:body.byteLength,chunk:chunks});nativeFinish(1);return;}stored=nativeStoreMedia(body,offset===0,end===length-1);chunks++;}
     emit('media_bounded_download','pass',{elapsed_ms:Date.now()-started,bytes:stored,chunks});emit('media_saved','pass',{bytes:stored,slot:PROBE_MODE.endsWith('next')?'next':'first'});nativeFinish(0);return;
   }
   started=Date.now();const response=await fetch(url,{headers:{Range:full?'bytes=0-16777215':'bytes=0-65535'},signal:AbortSignal.timeout(15000)});const body=await response.arrayBuffer();emit(full?'media_bounded_download':'media_first_bytes',response.ok&&body.byteLength>0?'pass':'fail',{elapsed_ms:Date.now()-started,http_status:response.status,bytes:body.byteLength});if(full&&response.ok){const saved=nativeStoreMedia(body);emit('media_saved','pass',{bytes:saved,slot:PROBE_MODE.endsWith('next')?'next':'first'});}nativeFinish(response.ok?0:1);
 }catch(e){emit('media_resolution','fail',{elapsed_ms:Date.now()-started,...error(e)});nativeFinish(1);}
}
main().catch(e=>{emit('probe','fail',error(e));nativeFinish(1);});
