// SPDX-License-Identifier: MIT
// Independent implementation informed by YouTubeKit's MIT preroll schema at
// 7f75a2299dc329c0b7855afb25d47663a02855cb. See availability.md for provenance.

export const AVAILABILITY_LIMITS = Object.freeze({
  maxDepth: 24,
  maxNodes: 2048,
  maxContainerEntries: 64,
  maxPrerollCount: 64,
  maxStringLength: 4096,
  maxPlayerVarsBytes: 128 * 1024,
  maxDurationValueLength: 64,
  maxDeclaredDurationMs: 3_600_000,
  maxWaitMs: 120_000,
  maxUnixMs: 8_640_000_000_000_000,
});

const ABSENT = Symbol('absent');
const L = AVAILABILITY_LIMITS;
class Unknown extends Error {}
const fail = reason => { throw new Unknown(reason); };

/**
 * Inspect a decoded raw player JSON object before a library strips its ad data.
 * Known zero means no recognized advertised delay, not permission/playability.
 * This function neither sleeps nor requests media, and does not diagnose HTTP 403.
 */
export function extractAvailability(rawPlayerJson, receiptUnixMs) {
  return evaluateAvailability(rawPlayerJson, receiptUnixMs, null);
}

/** Bounded field-shape diagnostics, plus allowlisted public schema enum names. */
export function diagnoseAvailability(rawPlayerJson, receiptUnixMs) {
  const diagnostics = [];
  const availability = evaluateAvailability(rawPlayerJson, receiptUnixMs, row => diagnostics.push(Object.freeze(row)));
  return Object.freeze({ availability, diagnostics: Object.freeze(diagnostics) });
}

function evaluateAvailability(rawPlayerJson, receiptUnixMs, diagnostic) {
  let count = 0, nodes = 0;
  const seen = new Set();
  const result = (state, waitMs, reason) => Object.freeze({
    state,
    availableAtUnixMs: state === 'known' ? receiptUnixMs + waitMs : null,
    waitMs,
    reason,
    prerollCount: count,
  });
  const read = (object, key) => {
    const descriptor = Object.getOwnPropertyDescriptor(object, key);
    if (!descriptor) return ABSENT;
    if (!Object.hasOwn(descriptor, 'value')) fail('non_json_value');
    return descriptor.value;
  };
  const enter = (value, depth, isArray = false) => {
    if (depth > L.maxDepth || ++nodes > L.maxNodes) fail('traversal_limit');
    if (!value || typeof value !== 'object' || Array.isArray(value) !== isArray)
      fail('malformed_ad_shape');
    if (!isArray && ![Object.prototype, null].includes(Object.getPrototypeOf(value)))
      fail('non_json_value');
    if (seen.has(value)) fail('non_json_graph');
    seen.add(value);
    let keys = 0;
    for (const key in value) {
      if (Object.hasOwn(value, key) && ++keys > L.maxContainerEntries)
        fail('container_limit');
    }
    if (isArray && value.length > L.maxContainerEntries) fail('container_limit');
    return value;
  };
  const objectAt = (parent, key, depth) => enter(read(parent, key), depth);
  const arrayAt = (parent, key, depth) => enter(read(parent, key), depth, true);
  const string = (value, field, maxLength = L.maxStringLength) => {
    if (typeof value !== 'string' || value.length > maxLength) {
      // `field` is a constant category below, never a response key or value.
      diagnostic?.({ field, valueType: value === ABSENT ? 'absent' : value === null ? 'null' : typeof value,
        stringLength: typeof value === 'string' ? value.length : null });
      fail('invalid_string');
    }
    return value;
  };
  const rendererKind = (object, allowed) => {
    const present = allowed.filter(key => read(object, key) !== ABSENT);
    for (const key in object) {
      if (Object.hasOwn(object, key) && key.endsWith('Renderer') && !allowed.includes(key))
        fail('unknown_ad_renderer');
    }
    if (present.length !== 1) fail(present.length ? 'ambiguous_ad_layout' : 'unknown_ad_renderer');
    return present[0];
  };
  const duration = vars => {
    if (vars === ABSENT) return null;
    const text = string(vars, 'ad.player_vars', L.maxPlayerVarsBytes);
    const decode = value => decodeURIComponent(value.replace(/\+/g, ' '));
    let found = null, start = 0, separator = -1, pairCount = 0, utf8Bytes = 0, previousHighSurrogate = false;
    // One bounded scan. Do not split the full query or copy/decode unrelated
    // values: public ad playerVars may contain a large opaque tracking value.
    for (let index = 0; index <= text.length; index++) {
      const code = index < text.length ? text.charCodeAt(index) : -1;
      if (code >= 0) {
        // UTF-8 size without allocating an encoded copy. A paired low surrogate
        // contributes one byte after the preceding high surrogate's three.
        utf8Bytes += code >= 0xdc00 && code <= 0xdfff && previousHighSurrogate ? 1
          : code <= 0x7f ? 1 : code <= 0x7ff ? 2 : 3;
        previousHighSurrogate = code >= 0xd800 && code <= 0xdbff;
        if (utf8Bytes > L.maxPlayerVarsBytes) {
          diagnostic?.({ field: 'ad.player_vars', valueType: 'string', stringLength: text.length, utf8BytesObserved: utf8Bytes });
          fail('invalid_string');
        }
      }
      if (code === 61 && separator < 0) separator = index;
      if (code !== 38 && index !== text.length) continue;
      if (++pairCount > L.maxContainerEntries) {
        diagnostic?.({ field: 'ad.player_vars.pairs', valueType: 'string', stringLength: text.length, pairCount });
        fail('container_limit');
      }
      const keyEnd = separator < 0 ? index : separator;
      const keyLength = keyEnd - start;
      if (keyLength > L.maxStringLength) {
        diagnostic?.({ field: 'ad.player_vars.key', valueType: 'string', stringLength: keyLength });
        fail('invalid_string');
      }
      const key = decode(text.slice(start, keyEnd));
      if (key === 'length_seconds') {
        if (found !== null) fail('duplicate_duration');
        const valueStart = separator < 0 ? index : separator + 1;
        const valueLength = index - valueStart;
        if (valueLength > L.maxDurationValueLength) {
          diagnostic?.({ field: 'ad.player_vars.length_seconds', valueType: 'string', stringLength: valueLength });
          fail('invalid_duration');
        }
        const value = decode(text.slice(valueStart, index));
        if (!/^\d{1,7}(?:\.\d{1,3})?$/.test(value)) fail('invalid_duration');
        const point = value.indexOf('.');
        const whole = point < 0 ? value : value.slice(0, point);
        const fraction = point < 0 ? '' : value.slice(point + 1);
        found = Number(whole) * 1000 + Number(fraction.padEnd(3, '0'));
        if (!Number.isSafeInteger(found) || found > L.maxDeclaredDurationMs)
          fail('duration_limit');
      }
      start = index + 1;
      separator = -1;
    }
    return found;
  };
  const adWait = (ad, depth) => {
    enter(ad, depth);
    if (count === L.maxPrerollCount) fail('preroll_count_limit');
    count++;
    const skip = read(ad, 'skipOffsetMilliseconds');
    const declared = duration(read(ad, 'playerVars'));
    if (skip === ABSENT && declared === null) fail('missing_ad_timing');
    if (skip !== ABSENT && (!Number.isSafeInteger(skip) || skip < 0))
      fail('invalid_skip_offset');
    if (skip !== ABSENT && declared !== null && skip > declared)
      fail('conflicting_ad_timing');
    const wait = skip === ABSENT ? declared : skip;
    if (wait > L.maxWaitMs) fail('wait_limit');
    return wait;
  };
  const sum = values => {
    let total = 0;
    for (const value of values) {
      total += value;
      if (total > L.maxWaitMs) fail('wait_limit');
    }
    return total;
  };
  const each = (array, callback) => {
    const values = [];
    for (let index = 0; index < array.length; index++) {
      const value = read(array, String(index));
      if (value === ABSENT) fail('non_json_value');
      values.push(callback(value));
    }
    return values;
  };
  const webLayout = (value, depth) => {
    const layout = enter(value, depth);
    rendererKind(layout, ['playerBytesAdLayoutRenderer']);
    const renderer = objectAt(layout, 'playerBytesAdLayoutRenderer', depth + 1);
    const content = objectAt(renderer, 'renderingContent', depth + 2);
    const kind = rendererKind(content, ['instreamVideoAdRenderer', 'playerBytesSequentialLayoutRenderer']);
    if (kind === 'instreamVideoAdRenderer') return adWait(read(content, kind), depth + 3);
    const sequence = objectAt(content, kind, depth + 3);
    const layouts = arrayAt(sequence, 'sequentialLayouts', depth + 4);
    if (!layouts.length) fail('empty_preroll_sequence');
    return sum(each(layouts, child => webLayout(child, depth + 5)));
  };
  const tvContent = (value, depth, allowSequence = true) => {
    const content = enter(value, depth);
    const kind = rendererKind(content, allowSequence
      ? ['instreamVideoAdRenderer', 'linearAdSequenceRenderer'] : ['instreamVideoAdRenderer']);
    if (kind === 'instreamVideoAdRenderer') return adWait(read(content, kind), depth + 1);
    const sequence = objectAt(content, kind, depth + 1);
    const ads = arrayAt(sequence, 'linearAds', depth + 2);
    if (!ads.length) fail('empty_preroll_sequence');
    return sum(each(ads, child => tvContent(child, depth + 3, false)));
  };
  try {
    if (!Number.isSafeInteger(receiptUnixMs) || receiptUnixMs < 0 || receiptUnixMs > L.maxUnixMs)
      fail('invalid_receipt_time');
    const root = enter(rawPlayerJson, 0);
    let slotCount = 0, placementCount = 0;
    const waits = [];
    if (read(root, 'adSlots') !== ABSENT) {
      const slots = arrayAt(root, 'adSlots', 1);
      for (const slot of each(slots, value => enter(value, 2))) {
        rendererKind(slot, ['adSlotRenderer']);
        const renderer = objectAt(slot, 'adSlotRenderer', 3);
        const metadata = objectAt(renderer, 'adSlotMetadata', 4);
        const trigger = string(read(metadata, 'triggerEvent'), 'web.trigger_event');
        if (trigger === 'SLOT_TRIGGER_EVENT_LAYOUT_ID_ENTERED') continue;
        if (trigger !== 'SLOT_TRIGGER_EVENT_BEFORE_CONTENT') fail('unknown_slot_trigger');
        slotCount++;
        const fulfillment = objectAt(renderer, 'fulfillmentContent', 4);
        waits.push(webLayout(read(fulfillment, 'fulfilledLayout'), 5));
      }
    }
    if (read(root, 'adPlacements') !== ABSENT) {
      const placements = arrayAt(root, 'adPlacements', 1);
      for (const placement of each(placements, value => enter(value, 2))) {
        rendererKind(placement, ['adPlacementRenderer']);
        const renderer = objectAt(placement, 'adPlacementRenderer', 3);
        const config = objectAt(renderer, 'config', 4);
        const placementConfig = objectAt(config, 'adPlacementConfig', 5);
        const kind = string(read(placementConfig, 'kind'), 'tv.placement_kind');
        if (kind === 'AD_PLACEMENT_KIND_END') continue;
        if (kind !== 'AD_PLACEMENT_KIND_START') {
          // An exact public schema-enum shape may be logged, never arbitrary
          // field values. Comparing the full match rejects a trailing newline.
          const matched = /^AD_PLACEMENT_KIND_[A-Z_]{1,64}$/.exec(kind);
          diagnostic?.({ field: 'tv.placement_kind',
            enumValue: matched?.[0] === kind ? kind : 'unrecognized',
            valueType: 'string', stringLength: kind.length });
          if (diagnostic && kind === 'AD_PLACEMENT_KIND_MILLISECONDS') {
            // Inspect fixed data-property paths only; diagnostics must not invoke
            // accessors or change the subsequent validation decision.
            const peek = (object, key) => object && typeof object === 'object'
              ? Object.getOwnPropertyDescriptor(object, key) : undefined;
            const offsetDescriptor = peek(placementConfig, 'adTimeOffset');
            const offset = offsetDescriptor && Object.hasOwn(offsetDescriptor, 'value')
              ? offsetDescriptor.value : ABSENT;
            diagnostic({ field: 'tv.ad_time_offset', present: !!offsetDescriptor,
              valueType: offsetDescriptor && !Object.hasOwn(offsetDescriptor, 'value') ? 'accessor'
                : offset === ABSENT ? 'absent' : offset === null ? 'null' : typeof offset });
            for (const [key, field] of [
              ['offsetStartMilliseconds', 'tv.ad_time_offset.start_ms'],
              ['offsetEndMilliseconds', 'tv.ad_time_offset.end_ms'],
            ]) {
              const descriptor = peek(offset, key);
              const value = descriptor && Object.hasOwn(descriptor, 'value') ? descriptor.value : ABSENT;
              const numeric = typeof value === 'number' ? value
                : typeof value === 'string' && /^-?\d{1,16}$/.exec(value)?.[0] === value ? Number(value) : NaN;
              diagnostic({ field, present: !!descriptor,
                valueType: descriptor && !Object.hasOwn(descriptor, 'value') ? 'accessor'
                  : value === ABSENT ? 'absent' : value === null ? 'null' : typeof value,
                stringLength: typeof value === 'string' ? value.length : null,
                numericValue: Number.isSafeInteger(numeric) ? numeric : null });
            }
          }
          if (kind === 'AD_PLACEMENT_KIND_MILLISECONDS') {
            const offsets = objectAt(placementConfig, 'adTimeOffset', 6);
            const integerOffset = (value, allowEndSentinel = false) => {
              if (allowEndSentinel && (value === -1 || value === '-1')) return -1;
              const parsed = typeof value === 'number' ? value
                : typeof value === 'string' && /^\d{1,16}$/.exec(value)?.[0] === value ? Number(value) : NaN;
              if (!Number.isSafeInteger(parsed) || parsed < 0) fail('invalid_midroll_offset');
              return parsed;
            };
            const start = integerOffset(read(offsets, 'offsetStartMilliseconds'));
            const end = integerOffset(read(offsets, 'offsetEndMilliseconds'), true);
            // Only an explicitly later content-time range is outside the
            // initial preroll wait. Zero/unknown starts must never be skipped.
            if (start === 0 || (end !== -1 && end < start)) fail('invalid_midroll_offset');
            continue;
          }
          fail('unknown_placement_kind');
        }
        placementCount++;
        waits.push(tvContent(read(renderer, 'renderer'), 4));
      }
    }
    // These may be two representations of the same preroll. Timing/creative ID
    // alone cannot establish distinct occurrences, so never silently double-sum.
    if (slotCount && placementCount) fail('ambiguous_preroll_representations');
    const wait = sum(waits);
    if (receiptUnixMs > L.maxUnixMs - wait) fail('availability_time_overflow');
    return result('known', wait, count ? 'advertised_preroll' : 'no_advertised_preroll');
  } catch (error) {
    return result('unknown', null, error instanceof Unknown ? error.message : 'non_json_value');
  }
}
