// SPDX-License-Identifier: MIT
// Synthetic fixtures only. Node is a test tool, not a shipped runtime.
import assert from 'node:assert/strict';
import { buildPublicSamsungRequest, normalizeSamsungMetadata, TV_SAMSUNG_PROFILE as profile,
  PUBLIC_SAMPLE_IDS, CLIENT_PROFILE_LIMITS as limits } from './client-profiles.mjs';

let cases = 0;
const test = (name, operation) => { try { operation(); cases++; } catch (error) { error.message = `${name}: ${error.message}`; throw error; } };
const id = PUBLIC_SAMPLE_IDS[0];
const availability = Object.freeze({ state: 'unknown', waitMs: null, availableAtUnixMs: null, reason: 'fixture', prerollCount: 0 });
const binding = { videoId: id, receiptUnixMs: 1_794_348_000_000, availability };
const url = 'https://fixture.googlevideo.com/videoplayback?c=TVHTML5&cver=5.20260707&expire=1794350000&n=fixture%2Bvalue&sig=literal%2Fbytes';
const audio = { itag: 140, mimeType: 'audio/mp4; codecs="mp4a.40.2"', url, contentLength: '123456', audioSampleRate: '44100', audioChannels: 2, audioQuality: 'AUDIO_QUALITY_MEDIUM' };
const response = (streamingData = { adaptiveFormats: [audio] }) => ({
  playabilityStatus: { status: 'OK' }, videoDetails: { videoId: id }, streamingData,
});

test('exact pinned public request', () => {
  const options = { videoId: id, signatureTimestamp: 20340, visitorData: 'synthetic-public-visitor' };
  const request = buildPublicSamsungRequest(options);
  assert.deepEqual(Object.keys(request), ['url', 'method', 'headers', 'body']);
  assert.equal(request.url, 'https://www.youtube.com/youtubei/v1/player?prettyPrint=false');
  assert.equal(request.method, 'POST');
  assert.deepEqual(request.headers, {
    'Content-Type': 'application/json',
    'User-Agent': 'Mozilla/5.0 (SMART-TV; Linux; Tizen 2.4.0) AppleWebKit/538.1 (KHTML, like Gecko) Version/2.4.0 TV Safari/538.1',
    'accept-language': 'en-US,en', 'X-Goog-Visitor-Id': 'synthetic-public-visitor',
    Origin: 'https://www.youtube.com', 'X-Youtube-Client-Version': '5.20260707', 'X-Youtube-Client-Name': '7',
  });
  assert.deepEqual(JSON.parse(request.body), {
    context: { client: { clientName: 'TVHTML5', clientVersion: '5.20260707', deviceMake: 'Samsung', deviceModel: 'UKS9800', osName: 'Tizen', osVersion: '2.4.0' } },
    videoId: id, playbackContext: { contentPlaybackContext: { html5Preference: 'HTML5_PREF_WANTS', signatureTimestamp: 20340 } },
    contentCheckOk: true, racyCheckOk: true,
  });
  assert.deepEqual(options, { videoId: id, signatureTimestamp: 20340, visitorData: 'synthetic-public-visitor' });
  assert.equal(Object.isFrozen(request), true); assert.equal(Object.isFrozen(request.headers), true);
});
test('omitted optional upstream values remain omitted', () => {
  const r = buildPublicSamsungRequest({ videoId: PUBLIC_SAMPLE_IDS[1] });
  assert.equal(r.headers['X-Goog-Visitor-Id'], '');
  const body = JSON.parse(r.body);
  assert.deepEqual(body.playbackContext.contentPlaybackContext, { html5Preference: 'HTML5_PREF_WANTS' });
  for (const key of ['params', 'serviceIntegrityDimensions', 'thirdParty']) assert.equal(key in body, false);
  assert.equal('Cookie' in r.headers, false); assert.equal('Authorization' in r.headers, false);
});
for (const [name, options] of [
  ['non-sample ID', { videoId: 'other-public-id' }],
  ['negative STS', { videoId: id, signatureTimestamp: -1 }],
  ['unsafe STS', { videoId: id, signatureTimestamp: Number.MAX_SAFE_INTEGER }],
  ['fractional STS', { videoId: id, signatureTimestamp: 10.5 }],
  ['header newline', { videoId: id, visitorData: 'x\r\nAuthorization: x' }],
  ['visitor size', { videoId: id, visitorData: 'x'.repeat(4097) }],
  ['injected auth option', { videoId: id, authorization: 'not-allowed' }],
  ['profile override', { videoId: id, clientVersion: 'other' }],
]) test(name, () => assert.throws(() => buildPublicSamsungRequest(options), TypeError));

test('normalization retains provenance, URL bytes, expiry and availability', () => {
  const raw = response({ adaptiveFormats: [audio], expiresInSeconds: '0021600' });
  const frozenInput = JSON.stringify(raw);
  const result = normalizeSamsungMetadata(raw, binding);
  assert.equal(result.state, 'metadata'); assert.equal(result.reason, 'public_metadata_only');
  assert.equal(result.profile, profile); assert.equal(result.formats[0].profile, profile);
  assert.equal(result.availability, availability); assert.equal(result.receiptUnixMs, binding.receiptUnixMs);
  assert.equal(result.expiresInSecondsRaw, '0021600'); assert.equal(result.formats[0].url, url);
  assert.equal(result.formats[0].contentLength, 123456); assert.equal(result.formats[0].audioOnly, true);
  assert.equal(result.formats[0].transport, 'url_reference');
  assert.equal(JSON.stringify(raw), frozenInput); assert.equal(Object.isFrozen(result.formats[0]), true);
});
test('raw signature cipher is not decoded or rewritten', () => {
  const signatureCipher = 's=literal%2Bsig&sp=sig&url=https%3A%2F%2Ffixture.googlevideo.com%2Fv%3Fcver%3D5.20260707';
  const result = normalizeSamsungMetadata(response({ adaptiveFormats: [{ ...audio, url: undefined, signatureCipher }] }), binding);
  assert.equal(result.formats[0].signatureCipher, signatureCipher); assert.equal(result.formats[0].url, null);
  assert.equal(result.formats[0].transport, 'cipher_reference');
});
test('format occurrences remain separate across arrays', () => {
  const result = normalizeSamsungMetadata(response({ formats: [audio], adaptiveFormats: [audio] }), binding);
  assert.equal(result.formats.length, 2); assert.equal(result.formats[0].sourceArray, 'formats');
  assert.equal(result.formats[1].sourceArray, 'adaptiveFormats');
});
test('muxed and video-only classification', () => {
  const result = normalizeSamsungMetadata(response({ formats: [
    { ...audio, itag: 18, mimeType: 'video/mp4; codecs="avc1.42001E, mp4a.40.2"' },
    { itag: 137, mimeType: 'video/mp4; codecs="avc1.640028"', url },
  ] }), binding);
  assert.equal(result.formats[0].hasVideo, true); assert.equal(result.formats[0].hasAudio, true);
  assert.equal(result.formats[0].audioOnly, false); assert.equal(result.formats[1].hasAudio, false);
});
test('track identity retained without selecting dubbed/original', () => {
  const track = { id: 'fixture.en', displayName: 'Fixture', audioIsDefault: false };
  const r = normalizeSamsungMetadata(response({ adaptiveFormats: [{ ...audio, audioTrack: track }] }), binding);
  assert.deepEqual(r.formats[0].audioTrack, track); assert.equal(Object.isFrozen(track), false);
});
for (const [status, reason, expected] of [
  ['LOGIN_REQUIRED', 'Sign in', 'authentication_required'],
  ['UNPLAYABLE', 'Sign in to confirm you are not a bot', 'challenge_required'],
  ['UNPLAYABLE', 'Please log in', 'authentication_required'],
  ['AGE_CHECK_REQUIRED', '', 'provider_not_playable'],
  ['ERROR', 'Unavailable', 'provider_not_playable'],
]) test(`unsupported ${status} ${expected}`, () => {
  const raw = response(); raw.playabilityStatus = { status, reason };
  const r = normalizeSamsungMetadata(raw, binding);
  assert.equal(r.state, 'unsupported'); assert.equal(r.reason, expected); assert.equal(r.formats.length, 0);
});
test('mismatching recording rejected', () => {
  const raw = response(); raw.videoDetails.videoId = PUBLIC_SAMPLE_IDS[1];
  assert.equal(normalizeSamsungMetadata(raw, binding).reason, 'video_id_mismatch');
});
test('missing/malformed status rejected', () => {
  assert.equal(normalizeSamsungMetadata({}, binding).state, 'invalid');
  const raw = response(); raw.playabilityStatus = {};
  assert.equal(normalizeSamsungMetadata(raw, binding).reason, 'missing_playability_status');
});
test('SABR/HLS references stay separate from formats', () => {
  const r = normalizeSamsungMetadata(response({ serverAbrStreamingUrl: url, hlsManifestUrl: 'https://fixture.googlevideo.com/live.m3u8', onesieStreamingUrl: url, adaptiveFormats: [{ itag: 251, mimeType: 'audio/webm; codecs="opus"' }] }), binding);
  assert.equal(r.serverAbrStreamingUrl, url); assert.equal(r.formats[0].url, null);
  assert.equal(r.formats[0].transport, 'unresolved'); assert.equal(r.hlsManifestUrl, 'https://fixture.googlevideo.com/live.m3u8');
});
test('protected/malformed/unsafe formats have explicit rejection', () => {
  const r = normalizeSamsungMetadata(response({ adaptiveFormats: [
    { ...audio, drmFamilies: ['fixture-drm'] },
    { ...audio, contentLength: '9007199254740992' },
    { ...audio, url: 'http://fixture.example/media' },
    { ...audio, url: '', signatureCipher: 'x' },
  ] }), binding);
  assert.equal(r.formats.length, 0);
  assert.deepEqual(r.rejectedFormats.map(x => x.reason), ['protected_format', 'malformed_format', 'unsupported_url', 'malformed_format']);
});
test('format count bound', () => assert.equal(normalizeSamsungMetadata(response({ adaptiveFormats: Array(limits.maxFormats + 1).fill(audio) }), binding).reason, 'format_count_or_shape'));
test('format array shape bound', () => assert.equal(normalizeSamsungMetadata(response({ adaptiveFormats: {} }), binding).reason, 'format_count_or_shape'));
test('bad expiry is invalid, never guessed', () => assert.equal(normalizeSamsungMetadata(response({ expiresInSeconds: '-1' }), binding).state, 'invalid'));
test('missing availability remains explicitly absent', () => assert.equal(normalizeSamsungMetadata(response(), { videoId: id, receiptUnixMs: 0 }).availability, null));
test('bad receipt and non-sample binding rejected', () => {
  assert.throws(() => normalizeSamsungMetadata(response(), { ...binding, receiptUnixMs: NaN }), TypeError);
  assert.throws(() => normalizeSamsungMetadata(response(), { ...binding, videoId: 'other' }), TypeError);
});
test('getters are not executed', () => {
  let touched = false; const raw = {};
  Object.defineProperty(raw, 'playabilityStatus', { get() { touched = true; throw new Error('no'); } });
  assert.equal(normalizeSamsungMetadata(raw, binding).state, 'invalid'); assert.equal(touched, false);
});
console.log(JSON.stringify({ gate: 'client_profile_fixtures', outcome: 'pass', cases, profile: profile.id, network: false }));
