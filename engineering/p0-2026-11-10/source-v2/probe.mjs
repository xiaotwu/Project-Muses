// MIT. Native P0 source integration. Public metadata and descriptors only in JS.
import '../source/shims.js';
import { Innertube, Platform, Log, Constants, Utils } from 'youtubei.js/web';
import { diagnoseAvailability } from './availability.mjs';
import { TV_SAMSUNG_PROFILE, buildPublicSamsungRequest, normalizeSamsungMetadata } from './client-profiles.mjs';

const emit = (gate, outcome, values = {}) => nativePrint(JSON.stringify({ gate, outcome, ...values }));
const classify = error => {
  const text = String(error?.message || '');
  if (/out of memory|stack overflow|interrupted/.test(text)) return 'runtime_limit';
  if (/sign in|bot|LOGIN_REQUIRED/i.test(text)) return 'authorization_or_challenge';
  if (/unavailable|unplayable/i.test(text)) return 'source_unavailable';
  if (/network_[-\d]+|timeout|aborted/.test(text)) return 'native_network';
  return 'redacted_source_error';
};
Log.setLevel(Log.Level.NONE);
const nativeFetch = globalThis.fetch;
let playerTiming;
async function observedFetch(input, options = {}) {
  const response = await nativeFetch(input, options);
  const requestURL = new URL(input instanceof Request ? input.url : String(input));
  if (requestURL.pathname === '/youtubei/v1/player' && response.ok) {
    const receiptUnixMs = Date.now();
    const raw = await response.clone().json();
    const requestBody = options.body ?? input?.body;
    let requestedId;
    try { requestedId = typeof requestBody === 'string' ? JSON.parse(requestBody).videoId : undefined; } catch {}
    const inspected = diagnoseAvailability(raw, receiptUnixMs);
    if (inspected.diagnostics.length) emit('source_availability_shape', 'observed', { diagnostics: inspected.diagnostics });
    playerTiming = {
      videoId: raw.videoDetails?.videoId ?? requestedId,
      client: SOURCE_CLIENT, receiptUnixMs,
      availability: inspected.availability
    };
  }
  return response;
}
Platform.load({
  runtime: 'muses-quickjs-p0-v2', server: true,
  Cache: class { async get() {} async set() {} async remove() {} },
  sha1Hash: async text => nativeSHA1(text), uuidv4: () => nativeUUID(),
  eval: data => {
    const result = JSON.parse(nativeEval(data.output));
    if (typeof result?.n === 'string' && result.n.startsWith('enhanced_except_'))
      throw new Error('isolated_solver_returned_error');
    return result;
  },
  fetch: observedFetch, Headers, Request, Response, FormData, File, ReadableStream, CustomEvent
});

async function decipherSamsung(format, player) {
  const cipherText = format.signature_cipher || format.cipher;
  const cipher = new URLSearchParams(cipherText || '');
  const reference = format.url || cipher.get('url');
  if (!reference) throw new Error('unsupported_stream_reference');
  const url = new URL(reference);
  const n = url.searchParams.get('n');
  const s = cipher.get('s');
  const sp = cipher.get('sp') || '';
  if (n === null && !s) return url.href;
  if (!player?.data?.output) throw new Error('descriptor_requires_player_solver');
  // The pinned helper interpolates these inputs into code. Reject unrecognized
  // alphabets before using it; never interpolate provider quotes/control text.
  if ((n !== null && !/^[A-Za-z0-9._~-]{1,2048}$/.test(n)) ||
      (s !== null && !/^[A-Za-z0-9._~-]{1,4096}$/.test(s)) || !/^[A-Za-z0-9_.-]{0,64}$/.test(sp))
    throw new Error('unsupported_solver_input');
  const output = `${player.data.output}\n${Utils.getNsigProcessorFn(n, sp, s)}`;
  const result = await Platform.shim.eval({ output });
  if (n !== null) {
    if (typeof result?.n !== 'string' || !result.n || result.n.startsWith('enhanced_except_')) throw new Error('invalid_solver_result');
    url.searchParams.set('n', result.n);
  }
  if (s) {
    if (typeof result?.sig !== 'string' || !result.sig) throw new Error('invalid_solver_result');
    url.searchParams.set(sp || 'signature', result.sig);
  }
  // Unlike Player.decipher's generic TV branch, keep this profile's cver intact.
  return url.href;
}

async function run() {
  const started = Date.now();
  const videoId = PROBE_MODE.endsWith('_next') ? 'eRsGyueVLvQ' : 'aqz-KE-bpKQ';
  const metadataOnly = PROBE_MODE === 'capabilities' || PROBE_MODE.startsWith('direct_');
  const yt = await Innertube.create({
    retrieve_player: !metadataOnly, generate_session_locally: false, fail_fast: true,
    enable_session_cache: false, timezone: 'America/Los_Angeles', lang: 'en',
    location: 'US', fetch: observedFetch
  });
  emit('session', 'pass', { elapsed_ms: Date.now() - started, player_loaded: !!yt.session.player });
  let info;
  if (SOURCE_CLIENT === 'TV_SAMSUNG') {
    const request = buildPublicSamsungRequest({ videoId,
      signatureTimestamp: yt.session.player?.signature_timestamp || null,
      visitorData: yt.session.context.client.visitorData || '' });
    const response = await observedFetch(request.url, request);
    const raw = await response.json();
    const normalized = normalizeSamsungMetadata(raw, { videoId, receiptUnixMs: playerTiming?.receiptUnixMs || Date.now(),
      availability: playerTiming?.availability });
    emit('source_profile', normalized.state === 'metadata' ? 'pass' : 'unsupported', {
      client: TV_SAMSUNG_PROFILE.id, client_version: TV_SAMSUNG_PROFILE.clientVersion,
      reason: normalized.reason, status: normalized.playabilityStatus,
      format_count: normalized.formats.length, rejected_formats: normalized.rejectedFormats.length
    });
    info = {
      playability_status: { status: normalized.playabilityStatus },
      streaming_data: {
        hls_manifest_url: normalized.hlsManifestUrl, server_abr_streaming_url: normalized.serverAbrStreamingUrl,
        adaptive_formats: normalized.formats.map(format => {
          const item = { has_audio: format.hasAudio, has_video: format.hasVideo, content_length: format.contentLength,
            mime_type: format.mimeType, bitrate: format.bitrate, itag: format.itag, url: format.url,
            signature_cipher: format.signatureCipher, cipher: format.cipher };
          item.decipher = player => decipherSamsung(item, player);
          return item;
        })
      }
    };
  } else info = await yt.getBasicInfo(videoId, { client: SOURCE_CLIENT });
  const formats = info.streaming_data?.adaptive_formats || [];
  const audio = formats.filter(format => format.has_audio && !format.has_video);
  const bounded = audio.filter(format => {
    const bytes = Number(format.content_length);
    return Number.isSafeInteger(bytes) && bytes > 0 && bytes <= 16 * 1024 * 1024;
  });
  const supported = bounded.filter(format => SOURCE_CODEC === 'opus'
    ? format.mime_type?.includes('opus') : format.mime_type?.includes('mp4a'));
  emit('source_capabilities', 'observed', {
    client: SOURCE_CLIENT, video_id: videoId, status: info.playability_status?.status || 'unknown',
    audio_formats: audio.length, bounded_audio_formats: bounded.length,
    requested_codec: SOURCE_CODEC, requested_codec_formats: supported.length,
    direct_formats: audio.filter(format => !!format.url).length,
    cipher_formats: audio.filter(format => !!format.signature_cipher || !!format.cipher).length,
    n_parameter_formats: audio.filter(format => format.url && new URL(format.url).searchParams.has('n')).length,
    hls: !!info.streaming_data?.hls_manifest_url,
    sabr: !!info.streaming_data?.server_abr_streaming_url
  });
  if (PROBE_MODE === 'capabilities') { nativeFinish(0); return; }
  if (!supported.length) {
    emit('source_representation', 'unsupported', { codec: SOURCE_CODEC });
    nativeFinish(2); return;
  }
  if (!playerTiming || playerTiming.videoId !== videoId || playerTiming.client !== SOURCE_CLIENT ||
      playerTiming.availability.state !== 'known') {
    emit('source_availability', 'unsupported', { reason: playerTiming?.availability.reason || 'missing_matching_player_response' });
    nativeFinish(2); return;
  }
  emit('source_availability', 'pass', { ...playerTiming.availability });
  const selected = supported.sort((a, b) => Number(b.bitrate || 0) - Number(a.bitrate || 0))[0];
  const originalN = selected.url ? new URL(selected.url).searchParams.get('n') : null;
  if (!yt.session.player && (originalN !== null || selected.signature_cipher || selected.cipher || !selected.url)) {
    emit('source_solver', 'unsupported', { reason: 'descriptor_requires_player_solver' });
    nativeFinish(2); return;
  }
  const resolved = new URL(await selected.decipher(yt.session.player));
  const expire = Number(resolved.searchParams.get('expire'));
  const descriptor = {
    version: 1, kind: 'direct', client: SOURCE_CLIENT, video_id: videoId,
    client_version: SOURCE_CLIENT === 'TV_SAMSUNG' ? TV_SAMSUNG_PROFILE.clientVersion : null,
    codec: SOURCE_CODEC, mime: selected.mime_type, itag: selected.itag,
    content_length: Number(selected.content_length), url: resolved.href,
    expires_unix_seconds: Number.isFinite(expire) && expire > 0 ? expire : 0,
    availability: playerTiming.availability,
    headers: Constants.STREAM_HEADERS
  };
  nativeDescriptor(JSON.stringify(descriptor));
  emit('source_descriptor', 'pass', {
    client: SOURCE_CLIENT, video_id: videoId, codec: SOURCE_CODEC,
    itag: selected.itag, content_length: descriptor.content_length,
    elapsed_ms: Date.now() - started, expires_known: descriptor.expires_unix_seconds > 0,
    n_present: originalN !== null, n_changed: originalN !== null && resolved.searchParams.get('n') !== originalN,
    signature_timestamp_known: Number(yt.session.player?.signature_timestamp) > 0,
    solver_required: originalN !== null || !!selected.signature_cipher || !!selected.cipher
  });
  nativeFinish(0);
}
run().catch(error => { emit('source_resolution', 'fail', { category: classify(error) }); nativeFinish(1); });
