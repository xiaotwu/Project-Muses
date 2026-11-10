// SPDX-License-Identifier: MIT
// Deterministic test process only; Node is not an application runtime dependency.
import assert from 'node:assert/strict';
import { extractAvailability, diagnoseAvailability, AVAILABILITY_LIMITS as limits } from './availability.mjs';

const receipt = 1_794_348_000_000;
const ad = (skipOffsetMilliseconds, playerVars) => ({
  ...(skipOffsetMilliseconds === undefined ? {} : { skipOffsetMilliseconds }),
  ...(playerVars === undefined ? {} : { playerVars }),
});
const layout = renderer => ({ playerBytesAdLayoutRenderer: { renderingContent: renderer } });
const web = renderer => ({ adSlots: [{ adSlotRenderer: {
  adSlotMetadata: { triggerEvent: 'SLOT_TRIGGER_EVENT_BEFORE_CONTENT' },
  fulfillmentContent: { fulfilledLayout: layout(renderer) },
} }] });
const tv = renderer => ({ adPlacements: [{ adPlacementRenderer: {
  config: { adPlacementConfig: { kind: 'AD_PLACEMENT_KIND_START' } }, renderer,
} }] });
const webAd = value => web({ instreamVideoAdRenderer: value });
const tvAd = value => tv({ instreamVideoAdRenderer: value });
const webSequence = values => web({ playerBytesSequentialLayoutRenderer: {
  sequentialLayouts: values.map(value => layout({ instreamVideoAdRenderer: value })),
} });
const tvSequence = values => tv({ linearAdSequenceRenderer: {
  linearAds: values.map(value => ({ instreamVideoAdRenderer: value })),
} });
let checks = 0;
const check = (name, raw, expected, time = receipt) => {
  const before = JSON.stringify(raw);
  const actual = extractAvailability(raw, time);
  assert.deepEqual(actual, {
    state: expected.state,
    availableAtUnixMs: expected.state === 'known' ? time + expected.waitMs : null,
    waitMs: expected.state === 'known' ? expected.waitMs : null,
    reason: expected.reason,
    prerollCount: expected.count,
  }, name);
  assert.equal(JSON.stringify(raw), before, `${name}: input remains unchanged`);
  assert.equal(Object.isFrozen(actual), true, `${name}: immutable result`);
  checks++;
};
const known = (waitMs, count, reason = count ? 'advertised_preroll' : 'no_advertised_preroll') =>
  ({ state: 'known', waitMs, count, reason });
const unknown = (reason, count = 0) => ({ state: 'unknown', count, reason });

check('absent ads', { videoDetails: { videoId: 'fixture' } }, known(0, 0));
check('empty ads', { adSlots: [], adPlacements: [] }, known(0, 0));
check('known skip beats declared duration', webAd(ad(5000, 'length_seconds=15')), known(5000, 1));
check('zero skip is advertised known zero', tvAd(ad(0, 'length_seconds=30')), known(0, 1));
check('duration precision', tvAd(ad(undefined, 'ignored=ok&length_seconds=2.125')), known(2125, 1));
check('encoded duration key', webAd(ad(undefined, 'length%5Fseconds=3')), known(3000, 1));
check('web sequential sum', webSequence([ad(5000), ad(undefined, 'length_seconds=3')]), known(8000, 2));
check('TV sequential sum', tvSequence([ad(2000), ad(undefined, 'length_seconds=4')]), known(6000, 2));
check('distinct same-duration occurrences remain distinct', tvSequence([ad(2000), ad(2000)]), known(4000, 2));
check('duplicate web/TV representations', { ...webAd(ad(5000)), ...tvAd(ad(5000)) }, unknown('ambiguous_preroll_representations', 2));
check('different timings cannot establish separate representations', { ...webAd(ad(5000)), ...tvAd(ad(7000)) }, unknown('ambiguous_preroll_representations', 2));
check('midroll and postroll excluded before unknown payload', {
  adSlots: [{ adSlotRenderer: { adSlotMetadata: { triggerEvent: 'SLOT_TRIGGER_EVENT_LAYOUT_ID_ENTERED' } } }],
  adPlacements: [{ adPlacementRenderer: { config: { adPlacementConfig: { kind: 'AD_PLACEMENT_KIND_END' } }, renderer: { adBreakServiceRenderer: {} } } }],
}, known(0, 0));
check('unknown trigger', { adSlots: [{ adSlotRenderer: { adSlotMetadata: { triggerEvent: 'FUTURE_TRIGGER' } } }] }, unknown('unknown_slot_trigger'));
check('unknown placement', { adPlacements: [{ adPlacementRenderer: { config: { adPlacementConfig: { kind: 'FUTURE_KIND' } } } }] }, unknown('unknown_placement_kind'));
check('missing eligibility', { adSlots: [{ adSlotRenderer: {} }] }, unknown('malformed_ad_shape'));
check('unknown renderer', tv({ futureAdRenderer: {} }), unknown('unknown_ad_renderer'));
check('mixed renderer branches', tv({ instreamVideoAdRenderer: ad(1000), linearAdSequenceRenderer: { linearAds: [] } }), unknown('ambiguous_ad_layout'));
check('unknown renderer alongside known renderer', tv({ instreamVideoAdRenderer: ad(1000), futureAdRenderer: {} }), unknown('unknown_ad_renderer'));
check('empty preroll sequence', webSequence([]), unknown('empty_preroll_sequence'));
check('malformed ad array', { adSlots: 'unexpected' }, unknown('malformed_ad_shape'));
check('null ad array', { adSlots: null }, unknown('malformed_ad_shape'));
check('missing timing', tvAd(ad()), unknown('missing_ad_timing', 1));
check('malformed timing type', tvAd(ad('5000')), unknown('invalid_skip_offset', 1));
check('negative skip', webAd(ad(-1)), unknown('invalid_skip_offset', 1));
check('fractional skip', webAd(ad(1.5)), unknown('invalid_skip_offset', 1));
check('duplicate duration query', tvAd(ad(undefined, 'length_seconds=3&length_seconds=3')), unknown('duplicate_duration', 1));
check('conflicting skip and duration', tvAd(ad(6000, 'length_seconds=3')), unknown('conflicting_ad_timing', 1));
check('invalid duration', webAd(ad(undefined, 'length_seconds=1e3')), unknown('invalid_duration', 1));
check('invalid percent encoding', tvAd(ad(undefined, 'length%ZZseconds=3')), unknown('non_json_value', 1));
check('duration bound', tvAd(ad(undefined, 'length_seconds=3601')), unknown('duration_limit', 1));
check('individual wait bound', tvAd(ad(120001)), unknown('wait_limit', 1));
check('aggregate wait bound', tvSequence([ad(60001), ad(60000)]), unknown('wait_limit', 2));
check('exact wait ceiling accepted', tvAd(ad(120000)), known(120000, 1));
check('long skippable duration remains bounded by skip', tvAd(ad(5000, 'length_seconds=600')), known(5000, 1));
check('string bound', tvAd(ad(1000, 'x'.repeat(limits.maxStringLength + 1))), unknown('invalid_string', 1));
check('array bound', { adSlots: Array(limits.maxContainerEntries + 1).fill({}) }, unknown('container_limit'));
check('object bound', { adSlots: [], ...Object.fromEntries(Array.from({ length: limits.maxContainerEntries }, (_, i) => [`field${i}`, 0])) }, unknown('container_limit'));
check('sparse array rejected', { adSlots: Array(1) }, unknown('non_json_value'));
check('root is JSON text, not decoded object', '{}', unknown('malformed_ad_shape'));
check('null root', null, unknown('malformed_ad_shape'));
check('fractional receipt', {}, unknown('invalid_receipt_time'), receipt + 0.5);
check('negative receipt', {}, unknown('invalid_receipt_time'), -1);
check('receipt overflow', {}, unknown('invalid_receipt_time'), limits.maxUnixMs + 1);
check('result date overflow', webAd(ad(1)), unknown('availability_time_overflow', 1), limits.maxUnixMs);
let nested = { instreamVideoAdRenderer: ad(1) };
for (let i = 0; i < 6; i++) nested = { playerBytesSequentialLayoutRenderer: { sequentialLayouts: [layout(nested)] } };
check('depth bound', web(nested), unknown('traversal_limit'));
check('preroll count bound', { adPlacements: [
  ...tvSequence(Array.from({ length: limits.maxPrerollCount }, () => ad(1))).adPlacements,
  ...tvAd(ad(1)).adPlacements,
] }, unknown('preroll_count_limit', limits.maxPrerollCount));

// Non-JSON graphs/accessors are rejected without invoking the accessor.
let touched = false;
const accessor = {};
Object.defineProperty(accessor, 'adSlots', { enumerable: true, get() { touched = true; throw new Error('should not execute'); } });
assert.equal(extractAvailability(accessor, receipt).state, 'unknown');
assert.equal(touched, false);
const shared = ad(1);
assert.equal(extractAvailability(tvSequence([shared, shared]), receipt).reason, 'non_json_graph');
checks += 2;

// Unrelated metadata is not traversed; only consumed availability strings are
// bounded. Synthetic URLs here are fixtures, never captured provider values.
const longUnrelated = {
  videoDetails: { shortDescription: 'x'.repeat(limits.maxStringLength * 3) },
  streamingData: { adaptiveFormats: [{ url: 'https://example.invalid/' + 'x'.repeat(limits.maxStringLength * 3) }] },
};
check('long unrelated metadata without ads', longUnrelated, known(0, 0));
check('long unrelated metadata with recognized ads', { ...longUnrelated, ...tvAd(ad(1000, 'length_seconds=3')) }, known(1000, 1));
check('long real ad remains unknown beside unrelated metadata', { ...longUnrelated, ...tvAd(ad(1000, 'x'.repeat(limits.maxStringLength + 1))) }, unknown('invalid_string', 1));

for (const [name, raw, field, valueType, stringLength] of [
  ['long playerVars', tvAd(ad(1000, 'x'.repeat(limits.maxPlayerVarsBytes + 1))), 'ad.player_vars', 'string', limits.maxPlayerVarsBytes + 1],
  ['missing trigger', { adSlots: [{ adSlotRenderer: { adSlotMetadata: {} } }] }, 'web.trigger_event', 'absent', null],
  ['non-string placement kind', { adPlacements: [{ adPlacementRenderer: { config: { adPlacementConfig: { kind: 1 } } } }] }, 'tv.placement_kind', 'number', null],
]) {
  const inspected = diagnoseAvailability(raw, receipt);
  assert.deepEqual(inspected.availability, extractAvailability(raw, receipt), `${name}: diagnostics preserve behavior`);
  assert.deepEqual(inspected.diagnostics, [{ field, valueType, stringLength }], name);
  assert.equal(Object.isFrozen(inspected) && Object.isFrozen(inspected.diagnostics) && Object.isFrozen(inspected.diagnostics[0]), true);
  checks++;
}
const normalInspection = diagnoseAvailability({ ...longUnrelated, ...tvAd(ad(1000)) }, receipt);
assert.equal(normalInspection.availability.state, 'known');
assert.deepEqual(normalInspection.diagnostics, []);
checks++;

const varsOfLength = (length, suffix = '&length_seconds=30') =>
  'opaque=' + 'x'.repeat(length - 'opaque='.length - suffix.length) + suffix;
const observedLengthFixture = varsOfLength(97_203);
assert.equal(observedLengthFixture.length, 97_203);
check('observed-length opaque value with skip', tvAd(ad(5000, observedLengthFixture)), known(5000, 1));
check('observed-length opaque value with duration', tvAd(ad(undefined, observedLengthFixture)), known(30000, 1));
check('playerVars exact independent byte ceiling', tvAd(ad(undefined, varsOfLength(limits.maxPlayerVarsBytes, '&length_seconds=3'))), known(3000, 1));
check('playerVars byte ceiling exceeded', tvAd(ad(1000, varsOfLength(limits.maxPlayerVarsBytes + 1))), unknown('invalid_string', 1));
check('large opaque value keeps duplicate timing fail-closed', tvAd(ad(undefined, 'length_seconds=3&' + observedLengthFixture)), unknown('duplicate_duration', 1));
check('encoded timing key after large opaque value', tvAd(ad(undefined, varsOfLength(97_203, '&length%5Fseconds=2.125'))), known(2125, 1));
check('unrelated opaque value is not percent-decoded', tvAd(ad(undefined, 'opaque=%ZZ' + 'x'.repeat(97_000) + '&length_seconds=3')), known(3000, 1));
check('recognized duration raw value remains small', tvAd(ad(undefined, 'length_seconds=' + '1'.repeat(limits.maxDurationValueLength + 1))), unknown('invalid_duration', 1));
check('encoded recognized duration is bounded before decoding', tvAd(ad(undefined, 'length_seconds=' + '%31'.repeat(30))), unknown('invalid_duration', 1));
check('encoded small recognized duration accepted', tvAd(ad(undefined, 'length_seconds=%32%2E%31%32%35')), known(2125, 1));
check('64 query pairs stay allowed', tvAd(ad(undefined, Array.from({ length: 63 }, (_, i) => `k${i}=x`).join('&') + '&length_seconds=3')), known(3000, 1));
const tooManyPairs = Array.from({ length: 64 }, (_, i) => `k${i}=x`).join('&') + '&length_seconds=3';
check('65 query pairs remain unknown', tvAd(ad(undefined, tooManyPairs)), unknown('container_limit', 1));
assert.deepEqual(diagnoseAvailability(tvAd(ad(undefined, tooManyPairs)), receipt).diagnostics,
  [{ field: 'ad.player_vars.pairs', valueType: 'string', stringLength: tooManyPairs.length, pairCount: 65 }]);
checks++;
check('UTF-8 byte ceiling, not only UTF-16 length', tvAd(ad(undefined, 'opaque=' + '汉'.repeat(44_000) + '&length_seconds=3')), unknown('invalid_string', 1));
check('paired surrogate byte accounting', tvAd(ad(undefined, 'opaque=' + '😀'.repeat(20_000) + '&length_seconds=3')), known(3000, 1));
check('long metadata does not weaken ad depth bound', { ...longUnrelated, ...web(nested) }, unknown('traversal_limit'));

for (const [kind, enumValue] of [
  ['AD_PLACEMENT_KIND_FUTURE', 'AD_PLACEMENT_KIND_FUTURE'],
  ['https://example.invalid/private?token=fixture', 'unrecognized'],
  ['AD_PLACEMENT_KIND_FUTURE\n', 'unrecognized'],
  ['AD_PLACEMENT_KIND_' + 'A'.repeat(65), 'unrecognized'],
  ['AD_PLACEMENT_KIND_FUTURE1', 'unrecognized'],
  ['AD_PLACEMENT_KIND_future', 'unrecognized'],
]) {
  const raw = { adPlacements: [{ adPlacementRenderer: { config: { adPlacementConfig: { kind } } } }] };
  const inspected = diagnoseAvailability(raw, receipt);
  assert.deepEqual(inspected.availability, { state: 'unknown', availableAtUnixMs: null, waitMs: null,
    reason: 'unknown_placement_kind', prerollCount: 0 });
  assert.deepEqual(inspected.availability, extractAvailability(raw, receipt));
  assert.deepEqual(inspected.diagnostics, [{ field: 'tv.placement_kind', enumValue, valueType: 'string', stringLength: kind.length }]);
  if (enumValue === 'unrecognized') assert.equal(JSON.stringify(inspected.diagnostics).includes(kind), false);
  checks++;
}

const offsetFixture = offsets => ({ adPlacements: [{ adPlacementRenderer: { config: { adPlacementConfig: {
  kind: 'AD_PLACEMENT_KIND_MILLISECONDS', adTimeOffset: offsets,
} } } }] });
for (const [start, end, expectedStart, expectedEnd] of [
  ['120000', '180000', 120000, 180000], [120000, -1, 120000, -1],
  ['https://example.invalid/private?token=fixture', '300000\n', null, null],
  ['1'.repeat(17), '9007199254740992', null, null],
]) {
  const raw = offsetFixture({ offsetStartMilliseconds: start, offsetEndMilliseconds: end });
  const inspected = diagnoseAvailability(raw, receipt);
  assert.deepEqual(inspected.availability, extractAvailability(raw, receipt));
  assert.equal(inspected.availability.reason, expectedStart !== null && expectedEnd !== null
    ? 'no_advertised_preroll' : 'invalid_midroll_offset');
  assert.equal(inspected.diagnostics.length, 4);
  assert.deepEqual(inspected.diagnostics[1], { field: 'tv.ad_time_offset', present: true, valueType: 'object' });
  for (const [index, value, numericValue, field] of [[2, start, expectedStart, 'tv.ad_time_offset.start_ms'], [3, end, expectedEnd, 'tv.ad_time_offset.end_ms']]) {
    assert.deepEqual(inspected.diagnostics[index], { field, present: true, valueType: typeof value,
      stringLength: typeof value === 'string' ? value.length : null, numericValue });
  }
  if (typeof start === 'string' && start.startsWith('https:')) assert.equal(JSON.stringify(inspected.diagnostics).includes(start), false);
  checks++;
}
let offsetAccessorTouched = false;
const offsetAccessor = {};
Object.defineProperty(offsetAccessor, 'offsetStartMilliseconds', { enumerable: true, get() { offsetAccessorTouched = true; return 1000; } });
const accessorInspection = diagnoseAvailability(offsetFixture(offsetAccessor), receipt);
assert.equal(offsetAccessorTouched, false);
assert.equal(accessorInspection.availability.reason, 'non_json_value');
assert.deepEqual(accessorInspection.diagnostics[2], { field: 'tv.ad_time_offset.start_ms', present: true, valueType: 'accessor', stringLength: null, numericValue: null });
assert.deepEqual(accessorInspection.diagnostics[3], { field: 'tv.ad_time_offset.end_ms', present: false, valueType: 'absent', stringLength: null, numericValue: null });
checks++;

check('explicit positive midroll number range', offsetFixture({ offsetStartMilliseconds: 120000, offsetEndMilliseconds: 180000 }), known(0, 0));
check('explicit positive midroll string range', offsetFixture({ offsetStartMilliseconds: '120000', offsetEndMilliseconds: '180000' }), known(0, 0));
check('midroll end of content number sentinel', offsetFixture({ offsetStartMilliseconds: 120000, offsetEndMilliseconds: -1 }), known(0, 0));
check('midroll end of content string sentinel', offsetFixture({ offsetStartMilliseconds: '120000', offsetEndMilliseconds: '-1' }), known(0, 0));
check('positive point range is a content-time trigger', offsetFixture({ offsetStartMilliseconds: 120000, offsetEndMilliseconds: 120000 }), known(0, 0));
check('safe integer offset ceiling', offsetFixture({ offsetStartMilliseconds: Number.MAX_SAFE_INTEGER, offsetEndMilliseconds: Number.MAX_SAFE_INTEGER }), known(0, 0));
check('safe integer string offset ceiling', offsetFixture({ offsetStartMilliseconds: String(Number.MAX_SAFE_INTEGER), offsetEndMilliseconds: '-1' }), known(0, 0));
for (const [name, start, end] of [
  ['zero start', 0, 1000], ['string zero start', '0', '-1'], ['negative start', -1, -1],
  ['negative string start', '-1', '-1'], ['end before start', 2000, 1000], ['negative end', 1000, -2],
  ['missing start', undefined, -1], ['missing end', 1000, undefined], ['nonfinite start', Infinity, -1],
  ['nonfinite end', 1000, Infinity], ['fractional start', 1.5, -1], ['fractional end', 1000, 1000.5],
  ['unsafe start', Number.MAX_SAFE_INTEGER + 1, -1], ['unsafe end', 1000, Number.MAX_SAFE_INTEGER + 1],
  ['exponent string start', '1e3', '-1'], ['whitespace start', ' 1000', '-1'], ['newline end', '1000', '2000\n'],
  ['too long start string', '0'.repeat(16) + '1', '-1'], ['null start', null, -1], ['boolean end', 1000, true],
]) {
  check(`midroll rejects ${name}`, offsetFixture({ offsetStartMilliseconds: start, offsetEndMilliseconds: end }), unknown('invalid_midroll_offset'));
}
check('midroll missing offsets', offsetFixture(undefined), unknown('malformed_ad_shape'));
check('midroll malformed offsets array', offsetFixture([]), unknown('malformed_ad_shape'));
check('midroll retains object entry limit', offsetFixture({ offsetStartMilliseconds: 1000, offsetEndMilliseconds: -1,
  ...Object.fromEntries(Array.from({ length: 63 }, (_, i) => [`field${i}`, 0])) }), unknown('container_limit'));
check('valid midroll does not remove real TV preroll wait', { adPlacements: [
  ...offsetFixture({ offsetStartMilliseconds: 120000, offsetEndMilliseconds: -1 }).adPlacements,
  ...tvAd(ad(5000)).adPlacements,
] }, known(5000, 1));
check('valid midroll does not remove real web preroll wait', { ...webAd(ad(3000)),
  ...offsetFixture({ offsetStartMilliseconds: 120000, offsetEndMilliseconds: -1 }),
}, known(3000, 1));
check('valid midroll does not weaken overlapping preroll rejection', { ...webAd(ad(3000)), adPlacements: [
  ...offsetFixture({ offsetStartMilliseconds: 120000, offsetEndMilliseconds: -1 }).adPlacements,
  ...tvAd(ad(5000)).adPlacements,
] }, unknown('ambiguous_preroll_representations', 2));

console.log(JSON.stringify({ gate: 'availability_fixtures', outcome: 'pass', cases: checks, network: false, maxWaitMs: limits.maxWaitMs }));
