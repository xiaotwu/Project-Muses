// SPDX-License-Identifier: MIT
import { parseScript } from 'meriyah';
import { JsAnalyzer } from 'p0-upstream/utils/javascript/JsAnalyzer.js';
import { JsExtractor } from 'p0-upstream/utils/javascript/JsExtractor.js';
import { nsigMatcher,timestampMatcher } from 'p0-upstream/utils/javascript/matchers.js';
import { getNsigProcessorFn } from 'p0-upstream/utils/Utils.js';
import * as Log from 'p0-upstream/utils/Log.js';
Log.setLevel(Log.Level.NONE);
// Meriyah uses this only to copy its plain Identifier/StringLiteral records.
// Same scoped JSON clone as the frozen P0 shim, not a general Web API claim.
globalThis.structuredClone ??= value=>JSON.parse(JSON.stringify(value));
function phase(){
  nativeMark('before_parse');
  if(PROBE_PHASE==='parse_only'){
    let ast=parseScript(playerSource,{ranges:true,loc:false,module:false});
    nativeMark('after_parse');ast=null;playerSource=null;nativeGC();nativeMark('released');return;
  }
  let analyzer=new JsAnalyzer(playerSource,{extractions:[
    {friendlyName:'nsigFunction',match:nsigMatcher},
    {friendlyName:'signatureTimestampVar',match:timestampMatcher,collectDependencies:false}
  ]});
  nativeMark('after_analyzer');
  let extractor=new JsExtractor(analyzer);
  const result=extractor.buildScript({disallowSideEffectInitializers:true,exportRawValues:true,rawValueOnly:['signatureTimestampVar']});
  nativeMark('after_extractor');
  if(!result.exported.includes('nsigFunction')||!Number(result.exportedRawValues?.signatureTimestampVar))throw Error('target_missing');
  globalThis.solverText=result.output;
  globalThis.signatureTimestamp=Number(result.exportedRawValues.signatureTimestampVar);
  // Synthetic inputs only. Real provider challenge tokens remain caller-owned.
  globalThis.testText=result.output+'\n'+getNsigProcessorFn('0123456789abcdef','sig','ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789');
  analyzer=null;extractor=null;playerSource=null;nativeGC();nativeMark('released');
}
phase();
