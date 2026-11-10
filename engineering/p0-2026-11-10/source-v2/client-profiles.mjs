// SPDX-License-Identifier: MIT
// Independently implemented from the public MIT YouTubeKit schema/profile at
// 7f75a2299dc329c0b7855afb25d47663a02855cb. See client-profiles.md.

export const PUBLIC_SAMPLE_IDS = Object.freeze(['aqz-KE-bpKQ', 'eRsGyueVLvQ']);
export const TV_SAMSUNG_PROFILE = Object.freeze({
  id: 'TV_SAMSUNG',
  sourceLibrary: 'YouTubeKit',
  sourceCommit: '7f75a2299dc329c0b7855afb25d47663a02855cb',
  clientName: 'TVHTML5',
  clientVersion: '5.20260707',
  clientHeaderId: '7',
  userAgent: 'Mozilla/5.0 (SMART-TV; Linux; Tizen 2.4.0) AppleWebKit/538.1 (KHTML, like Gecko) Version/2.4.0 TV Safari/538.1',
  deviceMake: 'Samsung',
  deviceModel: 'UKS9800',
  osName: 'Tizen',
  osVersion: '2.4.0',
});
export const CLIENT_PROFILE_LIMITS = Object.freeze({
  maxFormats: 256,
  maxReferenceLength: 32768,
  maxTextLength: 4096,
  maxUnixMs: 8_640_000_000_000_000,
});

const P = TV_SAMSUNG_PROFILE;
const L = CLIENT_PROFILE_LIMITS;
const absent = Symbol('absent');
const record = value => {
  if (!value || typeof value !== 'object' || Array.isArray(value)
      || ![Object.prototype, null].includes(Object.getPrototypeOf(value)))
    throw new TypeError('Expected decoded JSON object');
  return value;
};
const read = (value, key) => {
  const property = Object.getOwnPropertyDescriptor(value, key);
  if (!property) return absent;
  if (!Object.hasOwn(property, 'value')) throw new TypeError('Accessor is not decoded JSON');
  return property.value;
};
const optional = value => value === absent || value === null || value === undefined;
const stringOrNull = (value, max = L.maxTextLength) => {
  if (optional(value)) return null;
  if (typeof value !== 'string' || value.length > max) throw new TypeError('Invalid bounded text');
  return value;
};
const integerOrNull = value => {
  if (optional(value)) return null;
  if (typeof value === 'string' && /^\d{1,16}$/.test(value)) value = Number(value);
  if (!Number.isSafeInteger(value) || value < 0) throw new TypeError('Invalid nonnegative integer');
  return value;
};
const sample = videoId => {
  if (!PUBLIC_SAMPLE_IDS.includes(videoId)) throw new TypeError('Public sample ID required');
  return videoId;
};

/** Build the pinned, unauthenticated public request. Performs no I/O. */
export function buildPublicSamsungRequest(options) {
  record(options);
  for (const key of Object.keys(options)) {
    if (!['videoId', 'signatureTimestamp', 'visitorData'].includes(key))
      throw new TypeError('Unsupported request option');
  }
  const videoId = sample(read(options, 'videoId'));
  const signatureTimestamp = integerOrNull(read(options, 'signatureTimestamp'));
  if (signatureTimestamp !== null && signatureTimestamp > 2_147_483_647)
    throw new TypeError('Invalid signature timestamp');
  const visitorData = stringOrNull(read(options, 'visitorData')) ?? '';
  if (/[^\x20-\x7e]/.test(visitorData)) throw new TypeError('Invalid visitor header');
  const contentPlaybackContext = {
    html5Preference: 'HTML5_PREF_WANTS',
    ...(signatureTimestamp === null ? {} : { signatureTimestamp }),
  };
  return Object.freeze({
    url: 'https://www.youtube.com/youtubei/v1/player?prettyPrint=false',
    method: 'POST',
    headers: Object.freeze({
      'Content-Type': 'application/json',
      'User-Agent': P.userAgent,
      'accept-language': 'en-US,en',
      'X-Goog-Visitor-Id': visitorData,
      Origin: 'https://www.youtube.com',
      'X-Youtube-Client-Version': P.clientVersion,
      'X-Youtube-Client-Name': P.clientHeaderId,
    }),
    body: JSON.stringify({
      context: { client: {
        clientName: P.clientName,
        clientVersion: P.clientVersion,
        deviceMake: P.deviceMake,
        deviceModel: P.deviceModel,
        osName: P.osName,
        osVersion: P.osVersion,
      } },
      videoId,
      playbackContext: { contentPlaybackContext },
      contentCheckOk: true,
      racyCheckOk: true,
    }),
  });
}

const normalizeFormat = (raw, sourceArray, index) => {
  record(raw);
  const itag = integerOrNull(read(raw, 'itag'));
  const mimeType = stringOrNull(read(raw, 'mimeType'), 512);
  if (!itag || !mimeType || !/^(audio|video)\/[A-Za-z0-9.+-]+(?:;|$)/.test(mimeType))
    throw new TypeError('Invalid format identity');
  const drm = read(raw, 'drmFamilies');
  if (!optional(drm)) {
    if (!Array.isArray(drm) || drm.length > 16) throw new TypeError('Malformed protection metadata');
    if (drm.length) return { rejected: 'protected_format' };
  }
  const url = stringOrNull(read(raw, 'url'), L.maxReferenceLength);
  const signatureCipher = stringOrNull(read(raw, 'signatureCipher'), L.maxReferenceLength);
  const cipher = stringOrNull(read(raw, 'cipher'), L.maxReferenceLength);
  if ([url, signatureCipher, cipher].some(value => value !== null && !value.length))
    throw new TypeError('Empty stream reference');
  if (url && (!url.startsWith('https://') || /[\u0000-\u0020\u007f]/.test(url)))
    return { rejected: 'unsupported_url' };
  if (signatureCipher && cipher && signatureCipher !== cipher)
    return { rejected: 'ambiguous_cipher' };
  const audioQuality = stringOrNull(read(raw, 'audioQuality'), 128);
  const audioSampleRate = integerOrNull(read(raw, 'audioSampleRate'));
  const audioChannels = integerOrNull(read(raw, 'audioChannels'));
  const hasVideo = mimeType.startsWith('video/');
  const hasAudio = mimeType.startsWith('audio/') || !!audioQuality
    || (audioSampleRate ?? 0) > 0 || (audioChannels ?? 0) > 0;
  const track = read(raw, 'audioTrack');
  let audioTrack = null;
  if (!optional(track)) {
    record(track);
    const isDefault = read(track, 'audioIsDefault');
    if (!optional(isDefault) && typeof isDefault !== 'boolean') throw new TypeError('Invalid track flag');
    audioTrack = Object.freeze({
      id: stringOrNull(read(track, 'id')),
      displayName: stringOrNull(read(track, 'displayName')),
      audioIsDefault: optional(isDefault) ? null : isDefault,
    });
  }
  return { format: Object.freeze({
    profile: P,
    sourceArray,
    sourceIndex: index,
    itag,
    mimeType,
    hasAudio,
    hasVideo,
    audioOnly: hasAudio && !hasVideo,
    bitrate: integerOrNull(read(raw, 'bitrate')),
    averageBitrate: integerOrNull(read(raw, 'averageBitrate')),
    contentLength: integerOrNull(read(raw, 'contentLength')),
    approxDurationMs: integerOrNull(read(raw, 'approxDurationMs')),
    audioSampleRate,
    audioChannels,
    audioQuality,
    audioTrack,
    lastModified: stringOrNull(read(raw, 'lastModified'), 64),
    // These are untouched references, not resolved or transport-validated URLs.
    url,
    signatureCipher,
    cipher,
    transport: url ? 'url_reference' : (signatureCipher || cipher) ? 'cipher_reference' : 'unresolved',
  }) };
};

/**
 * Normalize public metadata only. Authentication/challenges stay unsupported.
 * URL/cipher bytes, advertised expiry and supplied availability are not rewritten.
 */
export function normalizeSamsungMetadata(rawPlayerJson, binding) {
  record(binding);
  const videoId = sample(read(binding, 'videoId'));
  const receiptUnixMs = read(binding, 'receiptUnixMs');
  if (!Number.isSafeInteger(receiptUnixMs) || receiptUnixMs < 0 || receiptUnixMs > L.maxUnixMs)
    throw new TypeError('Invalid receipt time');
  const suppliedAvailability = read(binding, 'availability');
  const availability = suppliedAvailability === absent ? null : suppliedAvailability;
  const finish = (state, reason, values = {}) => Object.freeze({
    state, reason, profile: P, videoId, receiptUnixMs, availability,
    playabilityStatus: null,
    expiresInSecondsRaw: null,
    hlsManifestUrl: null,
    serverAbrStreamingUrl: null,
    onesieStreamingUrl: null,
    formats: Object.freeze([]),
    rejectedFormats: Object.freeze([]),
    ...values,
  });
  try {
    const raw = record(rawPlayerJson);
    const playability = record(read(raw, 'playabilityStatus'));
    const status = stringOrNull(read(playability, 'status'), 64);
    const providerReason = stringOrNull(read(playability, 'reason')) ?? '';
    if (!status) return finish('invalid', 'missing_playability_status');
    const statusValue = { playabilityStatus: status };
    if (status === 'LOGIN_REQUIRED') return finish('unsupported', 'authentication_required', statusValue);
    if (/not a bot|confirm you.re|captcha|unusual traffic|automated quer/i.test(providerReason))
      return finish('unsupported', 'challenge_required', statusValue);
    if (/sign in|log in|login|authentication/i.test(providerReason))
      return finish('unsupported', 'authentication_required', statusValue);
    if (status !== 'OK') return finish('unsupported', 'provider_not_playable', statusValue);
    const details = record(read(raw, 'videoDetails'));
    if (read(details, 'videoId') !== videoId) return finish('invalid', 'video_id_mismatch', statusValue);
    const streaming = record(read(raw, 'streamingData'));
    const formats = [], rejectedFormats = [];
    let formatCount = 0;
    for (const sourceArray of ['formats', 'adaptiveFormats']) {
      const list = read(streaming, sourceArray);
      if (optional(list)) continue;
      if (!Array.isArray(list) || (formatCount += list.length) > L.maxFormats)
        return finish('invalid', 'format_count_or_shape', statusValue);
      for (let index = 0; index < list.length; index++) {
        try {
          const normalized = normalizeFormat(read(list, String(index)), sourceArray, index);
          if (normalized.format) formats.push(normalized.format);
          else rejectedFormats.push(Object.freeze({ sourceArray, sourceIndex: index, reason: normalized.rejected }));
        } catch {
          rejectedFormats.push(Object.freeze({ sourceArray, sourceIndex: index, reason: 'malformed_format' }));
        }
      }
    }
    const expires = read(streaming, 'expiresInSeconds');
    if (!optional(expires)) integerOrNull(expires); // Validate without changing representation or computing expiry.
    return finish('metadata', 'public_metadata_only', {
      ...statusValue,
      expiresInSecondsRaw: optional(expires) ? null : expires,
      hlsManifestUrl: stringOrNull(read(streaming, 'hlsManifestUrl'), L.maxReferenceLength),
      serverAbrStreamingUrl: stringOrNull(read(streaming, 'serverAbrStreamingUrl'), L.maxReferenceLength),
      onesieStreamingUrl: stringOrNull(read(streaming, 'onesieStreamingUrl'), L.maxReferenceLength),
      formats: Object.freeze(formats),
      rejectedFormats: Object.freeze(rejectedFormats),
    });
  } catch {
    return finish('invalid', 'malformed_player_metadata');
  }
}
