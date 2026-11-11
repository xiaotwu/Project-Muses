#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Bounded offline P0 corpus/campaign validation and honest attempt statistics.

No network, playback, account, global preferences or automatic freezing. Evidence
claims are checked for completeness, not independently certified by this tool.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import sys

MAX_DOCUMENT = 2 * 1024 * 1024
MAX_JOURNAL = 16 * 1024 * 1024
MAX_EVENTS = 10_000
SHA = re.compile(r"[0-9a-f]{64}\Z")
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z")
VIDEO = re.compile(r"[A-Za-z0-9_-]{11}\Z")
ZERO = "0" * 64
CONDITION_KEYS = (
    "process", "resolution", "media", "prefetch", "connection", "metadata",
    "os_cache", "account", "network", "route", "sample_rate_hz", "app_volume",
    "muted", "foreground", "environment_id", "measurement_id",
)
OUTCOMES = {
    "success", "player_error", "source_rejected", "source_changed", "network_error",
    "timeout", "wrong_recording", "cancelled", "manual_intervention", "measurement_invalid",
}
INVALID_MEASUREMENT = {"capture_failed", "clock_unsynchronized"}
FORBIDDEN_KEYS = {"cookie", "cookies", "authorization", "headers", "signedurl",
                  "mediaurl", "rawpayload", "visitordata", "accesstoken", "refreshtoken"}
FIELD_KEY = re.compile(r"[A-Za-z0-9_.-]{1,100}\Z")


class Invalid(ValueError):
    def __init__(self, path, code):
        self.path, self.code = path, code
        super().__init__(f"{path}: {code}")


def require(ok, path, code):
    if not ok:
        raise Invalid(path, code)


def obj(value, path):
    require(isinstance(value, dict), path, "expected_object")
    return value


def array(value, path, cap=1000):
    require(isinstance(value, list) and len(value) <= cap, path, "expected_bounded_array")
    return value


def text(value, path, cap=4096):
    require(isinstance(value, str) and 0 < len(value) <= cap, path, "expected_nonempty_text")
    return value


def identifier(value, path):
    require(isinstance(value, str) and ID.fullmatch(value) is not None, path, "invalid_identifier")
    return value


def number(value, path, minimum=0):
    require(type(value) in (int, float) and math.isfinite(value) and minimum <= value <= 2**53 - 1,
            path, "invalid_number")
    return value


def integer(value, path, minimum=0):
    number(value, path, minimum)
    require(type(value) is int, path, "expected_integer")
    return value


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(value, path):
    require(isinstance(value, str) and SHA.fullmatch(value) is not None, path, "invalid_sha256")
    return value


def timestamp(value, path):
    text(value, path, 64)
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        require(parsed.tzinfo is not None, path, "timezone_required")
    except ValueError:
        raise Invalid(path, "invalid_timestamp") from None
    return parsed


def scrub_shape(value, path="$", depth=0):
    require(depth <= 24, path, "depth_limit")
    if isinstance(value, dict):
        require(len(value) <= 128, path, "object_limit")
        for key, child in value.items():
            require(isinstance(key, str) and FIELD_KEY.fullmatch(key) is not None, path, "invalid_key")
            require(re.sub(r"[^a-z0-9]", "", key.lower()) not in FORBIDDEN_KEYS, path, "sensitive_field_not_allowed")
            scrub_shape(child, f"{path}.{key}", depth + 1)
    elif isinstance(value, list):
        require(len(value) <= MAX_EVENTS, path, "array_limit")
        for i, child in enumerate(value):
            scrub_shape(child, f"{path}[{i}]", depth + 1)
    elif isinstance(value, str):
        require(len(value) <= 4096, path, "string_limit")
        require("googlevideo.com" not in value.lower(), path, "signed_media_not_allowed")
    elif type(value) in (int, float):
        require(math.isfinite(value) and abs(value) <= 2**53 - 1, path, "invalid_json_number")
    else:
        require(value is None or type(value) is bool, path, "non_json_value")


def evidence(value, path):
    item = obj(value, path)
    text(item.get("reference"), path + ".reference")
    sha(item.get("sha256"), path + ".sha256")
    timestamp(item.get("observed_at"), path + ".observed_at")
    text(item.get("method"), path + ".method", 160)


def media_checks(checks, path):
    """Independent observations, never a single inferred 'playable' boolean."""
    obj(checks, path)
    required = {"media_transport", "media_decoded", "native_output_submitted", "audibility", "recording_identity"}
    require(set(checks) == required, path, "explicit_media_stages_required")
    for key in required:
        check = obj(checks[key], path + "." + key)
        accepted = "confirmed" if key in ("audibility", "recording_identity") else "passed"
        require(check.get("state") in ("unknown", "failed", accepted), path + "." + key, "invalid_check_state")
        if check["state"] != "unknown": evidence(check.get("evidence"), path + "." + key + ".evidence")
    transport = checks["media_transport"]; p = path + ".media_transport"
    require(transport.get("extent") in ("unknown", "initial_segment", "range_continuity", "complete"), p, "invalid_transport_extent")
    if transport["state"] == "passed":
        require(transport["extent"] != "unknown", p, "transport_extent_required")
        integer(transport.get("received_bytes"), p + ".received_bytes", 1)
        if transport.get("expected_bytes") is not None: integer(transport["expected_bytes"], p + ".expected_bytes", 1)
        if transport["extent"] == "complete":
            require(transport.get("expected_bytes") == transport["received_bytes"], p, "complete_transport_length_unverified")
    decoded = checks["media_decoded"]; p = path + ".media_decoded"
    require(decoded.get("extent") in ("unknown", "initial_segment", "complete"), p, "invalid_decode_extent")
    if decoded["state"] == "passed":
        require(decoded["extent"] != "unknown", p, "decode_extent_required")
        integer(decoded.get("decoded_frames"), p + ".decoded_frames", 1)
        fmt = obj(decoded.get("format"), p + ".format")
        require((fmt.get("codec"), fmt.get("container")) in (("aac", "m4a"), ("opus", "webm")), p, "invalid_observed_format")
        integer(fmt.get("sample_rate_hz"), p + ".format.sample_rate_hz", 1)
        channels = integer(fmt.get("channels"), p + ".format.channels", 1)
        require(channels <= 32, p, "channel_limit")
    native = checks["native_output_submitted"]; p = path + ".native_output_submitted"
    if native["state"] == "passed":
        integer(native.get("decoded_frames_consumed"), p + ".decoded_frames_consumed", 1)
        submitted = integer(native.get("submitted_frames"), p + ".submitted_frames", 1)
        nonzero = integer(native.get("nonzero_frames"), p + ".nonzero_frames")
        require(nonzero <= submitted, p, "nonzero_exceeds_submitted")
        require(type(native.get("muted")) is bool, p, "mute_state_required")
        require(not native["muted"] or nonzero == 0, p, "muted_post_gain_nonzero_conflict")


def decode_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "input", "duplicate_json_key")
            result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(Invalid("input", "nonfinite_json")))
    except (UnicodeError, json.JSONDecodeError):
        raise Invalid("input", "invalid_json") from None
    scrub_shape(value)
    return value


def read_json(path):
    path = Path(path)
    require(path.stat().st_size <= MAX_DOCUMENT, "input", "document_byte_limit")
    return decode_json(path.read_text())


def balanced_plan(case_ids, baseline_id, candidate_id, attempts, seed):
    """Frozen v1 scheduler: balanced repeats, seeded identity order, AB/BA pairs."""
    selected = sorted(case_ids)
    require(bool(selected) and len(selected) == len(set(selected)), "schedule", "invalid_case_ids")
    require(type(attempts) is int and len(selected)*3 <= attempts <= 1500, "schedule", "invalid_attempt_count")
    rng = random.Random(seed)
    quotient, remainder = divmod(attempts, len(selected))
    identities = selected * quotient + rng.sample(selected, remainder)
    rng.shuffle(identities)
    result = []
    for i, cid in enumerate(identities, 1):
        order = (baseline_id,candidate_id) if i % 2 else (candidate_id,baseline_id)
        for bid in order:
            result.append({"attempt_id":f"{bid}-{i:03d}","pair_id":f"pair-{i:03d}",
                           "case_id":cid,"build_id":bid,"stratum_id":"main_cold"})
    return result


def report(errors, gaps, summary):
    return {"valid": not errors, "freeze_ready": not errors and not gaps,
            "errors": errors, "freeze_gaps": gaps, "summary": summary}


def validate_corpus(data):
    errors, gaps = [], []
    summary = {"distinct_candidate_identities": 0, "metadata_verified_identities": 0,
               "media_transport_observed_identities": 0, "complete_transport_identities": 0,
               "media_decoded_identities": 0, "complete_decode_identities": 0,
               "native_output_submitted_identities": 0, "audibly_confirmed_identities": 0,
               "recording_identity_confirmed_identities": 0}
    try:
        scrub_shape(data)
        obj(data, "corpus")
        require(data.get("schema_version") == 1, "corpus.schema_version", "unsupported_version")
        identifier(data.get("corpus_id"), "corpus.corpus_id")
        require(data.get("status") in ("draft", "frozen"), "corpus.status", "invalid_status")
        cases = array(data.get("cases"), "corpus.cases", 500)
        by_id, identities, positives = {}, set(), []
        for i, case in enumerate(cases):
            p = f"corpus.cases[{i}]"; obj(case, p)
            cid = identifier(case.get("case_id"), p + ".case_id")
            require(cid not in by_id, p, "duplicate_case_id"); by_id[cid] = case
            require(case.get("role") in ("candidate", "positive"), p + ".role", "invalid_role")
            src = obj(case.get("source"), p + ".source")
            require(src.get("provider") == "youtube", p + ".source", "unsupported_provider")
            sid = src.get("id")
            require(isinstance(sid, str) and VIDEO.fullmatch(sid) is not None, p + ".source.id", "invalid_source_id")
            require(src.get("page") == "https://www.youtube.com/watch?v=" + sid, p + ".source.page", "noncanonical_page")
            require((src["provider"], sid) not in identities, p, "duplicate_source_identity")
            identities.add((src["provider"], sid))
            meta = obj(case.get("metadata"), p + ".metadata")
            text(meta.get("title"), p + ".metadata.title"); text(meta.get("artist"), p + ".metadata.artist")
            require(meta.get("state") in ("unknown", "page_title_observed", "catalog_observed", "verified"), p, "invalid_metadata_state")
            if meta.get("duration_ms") is not None: integer(meta["duration_ms"], p + ".duration_ms", 1)
            if meta.get("state") == "verified": evidence(meta.get("evidence"), p + ".metadata.evidence")
            languages = array(case.get("languages"), p + ".languages", 12)
            require(set(languages) <= {"zh", "ja", "latin", "other", "unknown"}, p, "invalid_language_tag")
            tags = array(case.get("tags"), p + ".tags", 32)
            require(all(isinstance(t, str) for t in tags), p, "invalid_tags")
            checks = obj(case.get("checks"), p + ".checks"); media_checks(checks, p + ".checks")
            if meta["state"] == "verified": summary["metadata_verified_identities"] += 1
            for stage, counter in (("media_transport", "media_transport_observed_identities"),
                                   ("media_decoded", "media_decoded_identities"),
                                   ("native_output_submitted", "native_output_submitted_identities")):
                if checks[stage]["state"] == "passed": summary[counter] += 1
            for stage, counter in (("media_transport", "complete_transport_identities"), ("media_decoded", "complete_decode_identities")):
                if checks[stage]["state"] == "passed" and checks[stage]["extent"] == "complete": summary[counter] += 1
            if checks["audibility"]["state"] == "confirmed": summary["audibly_confirmed_identities"] += 1
            if checks["recording_identity"]["state"] == "confirmed": summary["recording_identity_confirmed_identities"] += 1
            onset = obj(case.get("onset"), p + ".onset")
            require(onset.get("state") in ("unknown", "measured"), p + ".onset", "invalid_onset_state")
            if onset["state"] == "measured":
                number(onset.get("leading_silence_ms"), p + ".onset.leading_silence_ms")
                evidence(onset.get("evidence"), p + ".onset.evidence")
            caps = obj(case.get("capabilities"), p + ".capabilities")
            require(caps.get("state") in ("unknown", "observed"), p + ".capabilities", "invalid_capability_state")
            require(set(array(caps.get("formats"), p + ".formats", 8)) <= {"aac_m4a", "opus_webm"}, p, "invalid_format")
            for rate in array(caps.get("sample_rates_hz"), p + ".rates", 8): integer(rate, p + ".rate", 1)
            if caps["state"] == "observed": evidence(caps.get("evidence"), p + ".capabilities.evidence")
            for key in ("recording", "version", "account_condition", "region_condition", "retention_policy"):
                text(case.get(key), p + "." + key)
            ready = (all(checks[k]["state"] == "passed" for k in ("media_transport", "media_decoded", "native_output_submitted"))
                     and checks["audibility"]["state"] == "confirmed"
                     and checks["recording_identity"]["state"] == "confirmed" and meta["state"] == "verified"
                     and meta.get("duration_ms") is not None and onset["state"] == "measured" and caps["state"] == "observed"
                     and bool(caps["formats"]) and bool(caps["sample_rates_hz"])
                     and all(not any(word in case[k].lower() for word in ("unknown", "unverified"))
                             for k in ("recording", "version", "account_condition", "region_condition", "retention_policy")))
            if case["role"] == "positive" and ready: positives.append(case)
            else: gaps.append({"path": p, "code": "identity_not_verified_for_positive_group"})
        summary["distinct_candidate_identities"] = len(identities)
        summary["freeze_eligible_positives"] = len(positives)
        if len(positives) < 30: gaps.append({"path": "corpus.cases", "code": "need_30_verified_positive_identities"})
        positive_ids = {c["case_id"] for c in positives}
        groups = collections.Counter(); variants = set()
        for i, relation in enumerate(array(data.get("relationships"), "corpus.relationships", 100)):
            p = f"corpus.relationships[{i}]"; obj(relation, p)
            identifier(relation.get("relation_id"), p + ".relation_id")
            kind = relation.get("kind")
            require(kind in ("same_title", "version_family", "mv_audio"), p, "invalid_relationship_kind")
            members = array(relation.get("members"), p + ".members", 32)
            require(len(members) == len(set(members)) and set(members) <= set(by_id), p, "invalid_relationship_members")
            require(len(members) >= (3 if kind == "version_family" else 2), p, "insufficient_relationship_members")
            require(relation.get("state") in ("proposed", "reviewed"), p, "invalid_relationship_state")
            require(relation.get("timeline_equivalent") in ("unknown", True, False), p, "invalid_timeline_relation")
            require(relation.get("automatic_substitution") is False, p, "automatic_substitution_forbidden")
            if relation["state"] == "reviewed": evidence(relation.get("evidence"), p + ".evidence")
            if relation["state"] == "reviewed" and set(members) <= positive_ids:
                groups[kind] += 1
                if kind == "version_family": variants.update(array(relation.get("variants"), p + ".variants", 12))
        summary["reviewed_coverage_groups"] = dict(groups)
        for kind, minimum in (("same_title", 3), ("version_family", 2), ("mv_audio", 2)):
            if groups[kind] < minimum: gaps.append({"path": "corpus.relationships", "code": "missing_" + kind + "_coverage"})
        if not {"studio", "live", "original", "remix"} <= variants or not ({"radio_edit", "clean_explicit"} & variants):
            gaps.append({"path": "corpus.relationships", "code": "missing_version_variants"})
        for language in ("zh", "ja", "latin"):
            if sum(language in c["languages"] for c in positives) < 3:
                gaps.append({"path": "corpus.cases", "code": "missing_" + language + "_coverage"})
        tags = {t for c in positives for t in c["tags"]}
        for tag in ("mixed_script", "unicode_punctuation", "short_content", "long_content", "chaptered_podcast"):
            if tag not in tags: gaps.append({"path": "corpus.cases", "code": "missing_" + tag})
        formats = {f for c in positives for f in c["capabilities"]["formats"]}
        rates = {r for c in positives for r in c["capabilities"]["sample_rates_hz"]}
        if not {"aac_m4a", "opus_webm"} <= formats or len(rates) < 2:
            gaps.append({"path": "corpus.cases", "code": "missing_observed_media_diversity"})
        negatives = array(data.get("negative_cases"), "corpus.negative_cases", 64)
        confirmed_negative_kinds = set()
        for i, negative in enumerate(negatives):
            p = f"corpus.negative_cases[{i}]"; obj(negative, p)
            identifier(negative.get("case_id"), p + ".case_id")
            require(negative["case_id"] not in by_id, p, "duplicate_case_id"); by_id[negative["case_id"]] = negative
            require(negative.get("kind") in ("removed_or_nonexistent", "authorization_required", "region_or_account_restricted", "expired_resolution", "invalid_cache"), p, "invalid_negative_kind")
            text(negative.get("expected_error"), p + ".expected_error"); text(negative.get("recovery"), p + ".recovery")
            require(negative.get("state") in ("unknown", "verified"), p, "invalid_negative_state")
            if negative["state"] == "verified":
                evidence(negative.get("evidence"), p + ".evidence")
                source_id, source_case = negative.get("source_id"), negative.get("source_case_id")
                require((isinstance(source_id, str) and VIDEO.fullmatch(source_id) is not None)
                        or source_case in positive_ids, p, "negative_source_not_selected")
                confirmed_negative_kinds.add(negative["kind"])
        for kind in ("removed_or_nonexistent", "authorization_required", "region_or_account_restricted", "expired_resolution", "invalid_cache"):
            if kind not in confirmed_negative_kinds: gaps.append({"path": "corpus.negative_cases", "code": "unverified_" + kind})
        queue = obj(data.get("queue_context"), "corpus.queue_context")
        require(queue.get("state") in ("proposed", "verified"), "corpus.queue_context", "invalid_queue_state")
        if queue["state"] != "verified": gaps.append({"path": "corpus.queue_context", "code": "queue_context_unverified"})
        else: evidence(queue.get("evidence"), "corpus.queue_context.evidence")
        if data["status"] == "frozen":
            timestamp(data.get("frozen_at"), "corpus.frozen_at"); identifier(data.get("reviewer"), "corpus.reviewer")
            if gaps: errors.append({"path": "corpus.status", "code": "frozen_with_missing_evidence"})
    except Invalid as error:
        errors.append({"path": error.path, "code": error.code})
    except (TypeError, KeyError):
        errors.append({"path": "corpus", "code": "malformed_schema"})
    return report(errors, gaps, summary)


def conditions(value, path):
    value = obj(value, path)
    require(set(value) == set(CONDITION_KEYS), path, "incomplete_or_extra_conditions")
    for key in CONDITION_KEYS:
        if key == "sample_rate_hz": integer(value[key], path + "." + key, 1)
        elif key == "app_volume": require(0 <= number(value[key], path + "." + key) <= 1, path, "invalid_volume")
        elif key == "muted": require(type(value[key]) is bool, path, "invalid_mute")
        else: identifier(value[key], path + "." + key)
    return value


def validate_campaign(data, corpus):
    corpus_result = validate_corpus(corpus)
    errors, gaps, summary = [], [], {"planned_attempts": 0}
    try:
        scrub_shape(data); obj(data, "campaign")
        require(data.get("schema_version") == 1 and data.get("protocol_version") == 1, "campaign", "unsupported_version")
        identifier(data.get("campaign_id"), "campaign.campaign_id")
        require(data.get("status") in ("draft", "frozen"), "campaign.status", "invalid_status")
        require(data.get("platform") == "macos", "campaign.platform", "macos_only_campaign")
        require(data.get("corpus_sha256") == digest(corpus), "campaign.corpus_sha256", "corpus_hash_mismatch")
        if corpus.get("status") != "frozen" or not corpus_result["freeze_ready"]: gaps.append({"path": "campaign.corpus_sha256", "code": "corpus_not_frozen"})
        builds = obj(data.get("builds"), "campaign.builds")
        require(len(builds) == 2, "campaign.builds", "need_baseline_and_candidate")
        roles = {}
        for bid, build in builds.items():
            identifier(bid, "campaign.build_id"); obj(build, "campaign.build")
            role = build.get("role"); require(role in ("baseline", "candidate") and role not in roles, "campaign.build", "invalid_build_roles"); roles[role] = bid
            for key in ("artifact_sha256", "executable_sha256", "dependencies_sha256", "measurement_patch_sha256"):
                if build.get(key) is None: gaps.append({"path": f"campaign.builds.{bid}.{key}", "code": "build_not_frozen"})
                else: sha(build[key], "campaign.build." + key)
            if build.get("signature_verified") is not True or not build.get("source_revision") or not build.get("restrictions"):
                gaps.append({"path": f"campaign.builds.{bid}", "code": "build_provenance_incomplete"})
        require(builds[roles["baseline"]].get("version") == "0.6.3", "campaign.builds", "baseline_version_mismatch")
        measurement = obj(data.get("measurement"), "campaign.measurement")
        identifier(measurement.get("measurement_id"), "campaign.measurement_id")
        if measurement.get("capture_point") not in ("acoustic_output", "hardware_output_return"):
            gaps.append({"path": "campaign.measurement.capture_point", "code": "not_actual_output_measurement"})
        if measurement.get("calibration") is None: gaps.append({"path": "campaign.measurement.calibration", "code": "missing_calibration"})
        else: evidence(measurement["calibration"], "campaign.measurement.calibration")
        for key in ("tool_sha256", "detector_sha256", "clock_mapping_sha256", "noise_threshold_sha256", "evidence_window_policy_sha256", "cleanup_plan_sha256"):
            if measurement.get(key) is None: gaps.append({"path": "campaign.measurement." + key, "code": "measurement_not_frozen"})
            else: sha(measurement[key], "campaign.measurement." + key)
        for key in ("max_clock_error_ms", "max_capture_error_ms"):
            if measurement.get(key) is None: gaps.append({"path": "campaign.measurement." + key, "code": "measurement_error_unbounded"})
            else: number(measurement[key], "campaign.measurement." + key)
        environment = obj(data.get("environment"), "campaign.environment")
        identifier(environment.get("environment_id"), "campaign.environment.environment_id")
        for key in ("hardware_alias", "os_version", "os_build", "sdk", "compiler", "route_alias", "capture_chain", "network_observation", "isolation_policy"):
            if not environment.get(key) or environment[key] == "unknown": gaps.append({"path": "campaign.environment." + key, "code": "environment_not_frozen"})
        strata = obj(data.get("strata"), "campaign.strata")
        require(1 <= len(strata) <= 32, "campaign.strata", "invalid_strata_count")
        for sid, value in strata.items():
            identifier(sid, "campaign.stratum_id"); conditions(value, "campaign.strata." + sid)
            require(value["measurement_id"] == measurement["measurement_id"], "campaign.strata", "measurement_identity_mismatch")
            require(value["environment_id"] == environment["environment_id"], "campaign.strata", "environment_identity_mismatch")
        require("main_cold" in strata, "campaign.strata", "main_cold_missing")
        cold = strata["main_cold"]
        require(all(cold[k] == v for k, v in {"process":"new", "resolution":"miss", "media":"none", "prefetch":"none", "network":"reference", "foreground":"active"}.items()) and cold["muted"] is False,
                "campaign.strata.main_cold", "not_main_cold_conditions")
        policy = obj(data.get("policy"), "campaign.policy")
        require(policy.get("quantile") == "nearest_rank" and policy.get("no_sound") == "infinity", "campaign.policy", "invalid_statistics_policy")
        require(policy.get("invalid_replacement") == "append_once_same_plan_conditions" and policy.get("retry_clock") == "original_action", "campaign.policy", "invalid_attempt_policy")
        require(policy.get("thresholds") == {"p50_ms":2500, "p95_ms":5000, "success_rate":0.99}, "campaign.policy.thresholds", "unversioned_threshold_change")
        integer(policy.get("timeout_ms"), "campaign.policy.timeout_ms", 1)
        integer(policy.get("random_seed"), "campaign.policy.random_seed")
        require(policy.get("interleave_algorithm") == "balanced-shuffle-v1-paired-abba", "campaign.policy.interleave_algorithm", "unsupported_schedule_algorithm")
        integer(policy.get("scratch_limit_bytes"), "campaign.policy.scratch_limit_bytes", 1)
        integer(policy.get("free_floor_bytes"), "campaign.policy.free_floor_bytes", 1)
        plan = array(data.get("attempt_plan"), "campaign.attempt_plan", 3000)
        by_case = {c["case_id"]: c for c in corpus.get("cases", [])}
        ids, counts, paired = set(), collections.Counter(), collections.defaultdict(dict)
        for i, entry in enumerate(plan):
            p = f"campaign.attempt_plan[{i}]"; obj(entry, p)
            aid = identifier(entry.get("attempt_id"), p + ".attempt_id")
            require(aid not in ids, p, "duplicate_attempt_id"); ids.add(aid)
            require(entry.get("build_id") in builds and entry.get("case_id") in by_case and entry.get("stratum_id") in strata, p, "unknown_plan_reference")
            pair_id = identifier(entry.get("pair_id"), p + ".pair_id")
            require(entry["build_id"] not in paired[pair_id], p, "duplicate_pair_build")
            paired[pair_id][entry["build_id"]] = (entry["case_id"], entry["stratum_id"])
            counts[entry["build_id"], entry["stratum_id"], entry["case_id"]] += 1
        for pair in paired.values(): require(len(pair) == 2 and len(set(pair.values())) == 1, "campaign.attempt_plan", "unpaired_comparison_plan")
        main_sets = []
        for bid in builds:
            selected = {cid for b, s, cid in counts if b == bid and s == "main_cold"}
            main_sets.append(selected)
            if len(selected) < 30 or sum(counts[bid, "main_cold", c] for c in selected) < 100 or any(counts[bid, "main_cold", c] < 3 for c in selected):
                gaps.append({"path": "campaign.attempt_plan", "code": "need_100_attempts_30_ids_three_each_per_build"})
            for cid in selected:
                onset = by_case[cid].get("onset", {})
                if onset.get("state") != "measured" or onset.get("leading_silence_ms", math.inf) > 250:
                    gaps.append({"path": "campaign.attempt_plan", "code": "main_cold_onset_not_qualified"}); break
        require(main_sets[0] == main_sets[1], "campaign.attempt_plan", "different_comparison_corpora")
        baseline_count = sum(counts[roles["baseline"], "main_cold", c] for c in main_sets[0])
        if len(main_sets[0]) >= 30 and baseline_count >= len(main_sets[0])*3:
            expected_plan = balanced_plan(main_sets[0], roles["baseline"], roles["candidate"], baseline_count, policy["random_seed"])
            require([e for e in plan if e["stratum_id"] == "main_cold"] == expected_plan,
                    "campaign.attempt_plan", "seeded_schedule_mismatch")
        summary.update(planned_attempts=len(plan), pairs=len(paired), builds=list(builds), strata=list(strata))
        if data["status"] == "frozen":
            frozen_at = timestamp(data.get("frozen_at"), "campaign.frozen_at"); identifier(data.get("reviewer"), "campaign.reviewer")
            if measurement.get("calibration"):
                require(timestamp(measurement["calibration"]["observed_at"], "campaign.calibration.observed_at") <= frozen_at,
                        "campaign.measurement.calibration", "calibration_after_freeze")
            if gaps: errors.append({"path": "campaign.status", "code": "frozen_with_missing_evidence"})
    except Invalid as error:
        errors.append({"path": error.path, "code": error.code})
    except (TypeError, KeyError):
        errors.append({"path": "campaign", "code": "malformed_schema"})
    return report(errors, gaps, summary)


def nearest_rank(values, quantile):
    if not values: return None
    value = sorted(values)[math.ceil(quantile * len(values)) - 1]
    return "infinity" if math.isinf(value) else value


def wilson(successes, total):
    if not total: return None
    z = 1.959963984540054; p = successes / total
    denominator = 1 + z*z/total
    center = (p + z*z/(2*total)) / denominator
    spread = z * math.sqrt((p*(1-p) + z*z/(4*total))/total) / denominator
    return [max(0, center-spread), min(1, center+spread)]


def read_events(path):
    p = Path(path)
    require(p.stat().st_size <= MAX_JOURNAL, "journal", "journal_byte_limit")
    rows = []
    with p.open() as stream:
        for line in stream:
            require(len(rows) < MAX_EVENTS and len(line) <= 65536, "journal", "journal_event_limit")
            row = decode_json(line)
            rows.append(row)
    return rows


def chain_errors(events):
    errors, previous = [], ZERO
    for i, event in enumerate(events):
        try:
            scrub_shape(event); obj(event, f"events[{i}]")
            require(event.get("sequence") == i + 1 and event.get("previous_sha256") == previous,
                    f"events[{i}]", "journal_chain_mismatch")
            previous = digest(event)
        except (Invalid, ValueError) as error:
            errors.append({"path": getattr(error, "path", f"events[{i}]"), "code": getattr(error, "code", "invalid_json")})
            break
    return errors


def append_event(path, event):
    """Own-file append; never rewrites prior evidence. Chain is not a signature."""
    path = Path(path)
    require(not path.is_symlink(), "journal", "symlink_not_allowed")
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "a+b") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        require(os.fstat(stream.fileno()).st_size <= MAX_JOURNAL, "journal", "journal_byte_limit")
        stream.seek(0); rows = [decode_json(line) for line in stream]
        require(len(rows) < MAX_EVENTS and not chain_errors(rows), "journal", "invalid_existing_journal")
        require("sequence" not in event and "previous_sha256" not in event, "event", "caller_chain_fields_forbidden")
        row = {**event, "sequence":len(rows)+1, "previous_sha256":digest(rows[-1]) if rows else ZERO}
        scrub_shape(row); encoded = canonical(row) + b"\n"
        require(len(encoded) <= 65536 and os.fstat(stream.fileno()).st_size + len(encoded) <= MAX_JOURNAL, "journal", "journal_byte_limit")
        stream.write(encoded); stream.flush(); os.fsync(stream.fileno())
        return {"sequence":row["sequence"], "sha256":digest(row)}


def summarize(campaign, corpus, events):
    validation = validate_campaign(campaign, corpus)
    issues = list(validation["errors"]) + chain_errors(events)
    planned = {e["attempt_id"]:e for e in campaign.get("attempt_plan", [])}
    effective_plan = dict(planned)
    starts, finishes, replacements = {}, {}, {}
    planned_order, actual_base_order, in_flight = list(planned), [], set()
    for i, event in enumerate(events):
        p = f"events[{i}]"
        try:
            obj(event, p); require(event.get("campaign_sha256") == digest(campaign), p, "campaign_hash_mismatch")
            aid = identifier(event.get("attempt_id"), p + ".attempt_id")
            if aid not in effective_plan:
                original = event.get("replacement_for")
                prior = finishes.get(original, {})
                require(event.get("event") == "start" and original in planned and original not in replacements
                        and aid == original + ".replacement1" and prior.get("outcome") == "measurement_invalid"
                        and prior.get("measurement_error") in INVALID_MEASUREMENT, p, "unplanned_attempt")
                effective_plan[aid] = {**planned[original], "attempt_id":aid}
                replacements[original] = aid
            plan = effective_plan[aid]
            if event.get("event") == "start":
                require(aid not in starts, p, "duplicate_start")
                require(all(event.get(k) == plan[k] for k in ("case_id", "build_id", "stratum_id")), p, "plan_identity_mismatch")
                actual = conditions(event.get("conditions"), p + ".conditions")
                number(event.get("t_action_ms"), p + ".t_action_ms")
                identifier(event.get("clock_id"), p + ".clock_id")
                # Keep valid-shaped observations even when execution violated
                # the frozen order. Issues block inference, not preservation.
                if in_flight: issues.append({"path":p,"code":"overlapping_attempts"})
                if aid in planned:
                    index = len(actual_base_order)
                    if index >= len(planned_order) or aid != planned_order[index]:
                        issues.append({"path":p,"code":"actual_start_order_differs_from_frozen_plan"})
                    actual_base_order.append(aid)
                elif not all(base in finishes for base in planned):
                    issues.append({"path":p,"code":"replacement_before_base_plan_completed"})
                starts[aid] = event
                in_flight.add(aid)
                if actual != campaign["strata"][plan["stratum_id"]]: issues.append({"path": p, "code": "actual_conditions_differ_from_frozen_plan"})
            elif event.get("event") == "finish":
                require(aid in starts and aid not in finishes, p, "missing_start_or_duplicate_finish")
                require(event.get("outcome") in OUTCOMES, p, "invalid_outcome")
                integer(event.get("retry_count"), p + ".retry_count")
                actual_end = conditions(event.get("end_conditions"), p + ".end_conditions")
                finishes[aid] = event
                in_flight.discard(aid)
                if actual_end != starts[aid]["conditions"]:
                    issues.append({"path":p,"code":"conditions_changed_during_attempt"})
            else: require(False, p, "unknown_event")
        except Invalid as error: issues.append({"path": error.path, "code": error.code})
        except (TypeError, KeyError): issues.append({"path": p, "code": "malformed_event"})
    groups = {}
    cases = {c["case_id"]:c for c in corpus.get("cases", [])}
    for aid, start in starts.items():
        # Actual conditions are part of the key. Never silently mix a hot run,
        # account/network/route change with its nominal main-cold label.
        key = (start["build_id"], start["stratum_id"], digest(start["conditions"]))
        group = groups.setdefault(key, {"build_id":key[0], "stratum_id":key[1], "conditions":start["conditions"],
            "started":0, "measurement_invalid":0, "successes":0, "retry_count":0,
            "outcomes":collections.Counter(), "attempts":[], "latencies":[], "success_latencies":[]})
        group["started"] += 1
        end = finishes.get(aid)
        outcome = end["outcome"] if end else "unfinished"
        latency, valid, success = math.inf, True, False
        if end:
            group["retry_count"] += end["retry_count"]
            if outcome == "measurement_invalid":
                valid = False
                try:
                    require(end.get("measurement_error") in INVALID_MEASUREMENT, aid, "invalid_measurement_excuse")
                    evidence(end.get("evidence"), aid + ".evidence")
                except Invalid:
                    issues.append({"path": aid, "code": "invalid_measurement_excuse"})
                    valid = True; outcome = "unverified_failure"
            if outcome == "success":
                try:
                    sound = number(end.get("t_sound_ms"), aid + ".t_sound_ms")
                    require(sound >= start["t_action_ms"], aid, "sound_precedes_action")
                    require(sound-start["t_action_ms"] <= campaign["policy"]["timeout_ms"], aid, "success_after_observation_timeout")
                    require(end.get("clock_id") == start["clock_id"], aid, "clock_identity_mismatch")
                    require(end.get("onset_kind") == "actual_output" and end.get("target_content_confirmed") is True, aid, "no_verified_actual_sound")
                    require(end.get("measurement_id") == campaign["measurement"]["measurement_id"], aid, "measurement_identity_mismatch")
                    calibration = campaign["measurement"].get("calibration") or {}
                    require(end.get("calibration_sha256") == calibration.get("sha256") and calibration.get("sha256") is not None, aid, "calibration_mismatch")
                    require(end.get("final_source") == cases[start["case_id"]]["source"], aid, "wrong_source_identity")
                    evidence(end.get("evidence"), aid + ".evidence")
                    latency, success = sound-start["t_action_ms"], True
                except (Invalid, KeyError, TypeError) as error:
                    issues.append({"path":getattr(error,"path",aid), "code":getattr(error,"code","malformed_success")})
                    outcome = "unverified_sound"
        group["outcomes"][outcome] += 1
        if not valid: group["measurement_invalid"] += 1
        else: group["latencies"].append(latency)
        if success:
            group["successes"] += 1; group["success_latencies"].append(latency)
        group["attempts"].append({"attempt_id":aid,"outcome":outcome,"measurement_valid":valid,
            "sound_latency_ms":latency if math.isfinite(latency) else None,
            "right_censored":valid and not success, "retry_count":end["retry_count"] if end else 0})
    output = []
    for group in groups.values():
        latencies, success_latencies = group.pop("latencies"), group.pop("success_latencies")
        group.update(valid_measurements=len(latencies), success_rate_all_started=group["successes"]/group["started"],
            wilson_95_all_started=wilson(group["successes"],group["started"]),
            p50_ms=nearest_rank(latencies,.5),p95_ms=nearest_rank(latencies,.95),
            successful_only_p50_ms=nearest_rank(success_latencies,.5),successful_only_p95_ms=nearest_rank(success_latencies,.95))
        group["outcomes"] = dict(group["outcomes"]); output.append(group)
    missing = [aid for aid in planned if aid not in starts]
    unresolved_invalid = [aid for aid, end in finishes.items() if end["outcome"] == "measurement_invalid"
        and (aid not in replacements or replacements[aid] not in finishes
             or finishes[replacements[aid]]["outcome"] == "measurement_invalid")]
    incomplete = bool(missing or len(finishes) != len(starts) or unresolved_invalid)
    permitted = campaign.get("status") == "frozen" and validation["freeze_ready"] and not issues and not incomplete
    comparison = None
    if permitted:
        main = [g for g in output if g["stratum_id"] == "main_cold"]
        if len(main) != 2 or main[0]["conditions"] != main[1]["conditions"]:
            permitted = False; issues.append({"path":"comparison","code":"incomparable_actual_conditions"})
        else:
            comparison = [{"build_id":g["build_id"], "observed_thresholds_met":
                isinstance(g["p50_ms"],(int,float)) and g["p50_ms"] <= 2500 and
                isinstance(g["p95_ms"],(int,float)) and g["p95_ms"] <= 5000 and g["success_rate_all_started"] >= .99}
                for g in main]
    return {"scope":"actual-output attempt statistics; no production integration claim",
        "campaign_sha256":digest(campaign),"performance_conclusion_allowed":permitted,
        "validation":validation,"issues":issues,"planned":len(planned),"started":len(starts),
        "not_started_attempt_ids":missing,"journal_events":len(events),"groups":output,"comparison":comparison,
        "invalid_replacements":replacements,"unresolved_invalid_attempt_ids":unresolved_invalid,
        "actual_base_start_order":actual_base_order,"unfinished_attempt_ids":sorted(in_flight),
        "invalid_replacement_status":"At most one .replacement1 after every base-plan attempt finishes, serially, for a proven measurement failure; originals remain in all-started counts.",
        "confidence_note":"Wilson interval is descriptive; 100 observations do not establish universal 99% reliability."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    corpus = commands.add_parser("validate-corpus"); corpus.add_argument("corpus"); corpus.add_argument("--require-frozen", action="store_true")
    campaign = commands.add_parser("validate-campaign"); campaign.add_argument("campaign"); campaign.add_argument("corpus"); campaign.add_argument("--require-frozen", action="store_true")
    summary = commands.add_parser("summarize"); summary.add_argument("campaign"); summary.add_argument("corpus"); summary.add_argument("journal")
    append = commands.add_parser("append"); append.add_argument("journal"); append.add_argument("event")
    args = parser.parse_args()
    try:
        if args.command == "validate-corpus":
            data=read_json(args.corpus); result = validate_corpus(data)
            passed = result["valid"] and (not args.require_frozen or (result["freeze_ready"] and data.get("status")=="frozen"))
        elif args.command == "validate-campaign":
            data=read_json(args.campaign); result = validate_campaign(data,read_json(args.corpus))
            passed = result["valid"] and (not args.require_frozen or (result["freeze_ready"] and data.get("status")=="frozen"))
        elif args.command == "summarize":
            result = summarize(read_json(args.campaign),read_json(args.corpus),read_events(args.journal)); passed = not result["issues"]
        else: result = append_event(args.journal,read_json(args.event)); passed = True
        print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)); return 0 if passed else 2
    except (Invalid, OSError, ValueError) as error:
        print(json.dumps({"valid":False,"error":{"path":getattr(error,"path","input"),"code":getattr(error,"code",type(error).__name__)}})); return 2


if __name__ == "__main__":
    sys.exit(main())
