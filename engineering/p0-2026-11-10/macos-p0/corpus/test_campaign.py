#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Synthetic contract tests. No fixture claims to describe real playback."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
from campaign import (Invalid, ZERO, append_event, canonical, chain_errors, digest,
                      nearest_rank, read_events, read_json, summarize,
                      validate_campaign, validate_corpus)
from seed_draft import drafts


def proof(method="synthetic_fixture_only"):
    return {"reference":"synthetic-evidence.json","sha256":"1"*64,
            "observed_at":"2026-11-10T00:00:00Z","method":method}


def fixture():
    corpus, campaign = drafts()
    corpus["status"] = "frozen"; corpus["frozen_at"] = "2026-11-10T01:00:00Z"; corpus["reviewer"] = "synthetic-test"
    for case in corpus["cases"]:
        case["role"] = "positive"; case["metadata"].update(state="verified",duration_ms=180000,evidence=proof())
        case["recording"] = "synthetic-recording"; case["version"] = "synthetic-version"
        case["account_condition"] = "anonymous_public"; case["region_condition"] = "test-region"
        case["checks"]["media_transport"]={"state":"passed","extent":"complete","received_bytes":10000,"expected_bytes":10000,"evidence":proof()}
        case["checks"]["media_decoded"]={"state":"passed","extent":"initial_segment","decoded_frames":48000,
            "format":{"codec":"aac","container":"m4a","sample_rate_hz":48000,"channels":2},"evidence":proof()}
        case["checks"]["native_output_submitted"]={"state":"passed","decoded_frames_consumed":48000,
            "submitted_frames":48000,"nonzero_frames":40000,"muted":False,"evidence":proof()}
        for key, state in (("audibility","confirmed"),("recording_identity","confirmed")):
            case["checks"][key] = {"state":state,"evidence":proof()}
        case["onset"] = {"state":"measured","leading_silence_ms":0,"evidence":proof()}
        case["capabilities"] = {"state":"observed","formats":["aac_m4a","opus_webm"],"sample_rates_hz":[44100,48000],"offline_save":"unknown","evidence":proof()}
        case["tags"].append("short_content")
    for relation in corpus["relationships"]: relation.update(state="reviewed",evidence=proof())
    for negative in corpus["negative_cases"]: negative.update(state="verified",source_case_id="C028",evidence=proof())
    corpus["queue_context"].update(state="verified",evidence=proof())
    campaign["status"] = "frozen"; campaign["frozen_at"] = "2026-11-10T02:00:00Z"; campaign["reviewer"] = "synthetic-test"
    campaign["corpus_sha256"] = digest(corpus)
    for build in campaign["builds"].values():
        build.update(source_revision="synthetic-revision",signature_verified=True,restrictions="synthetic only")
        for key in ("artifact_sha256","executable_sha256","dependencies_sha256","measurement_patch_sha256"): build[key] = "2"*64
    measurement = campaign["measurement"]
    measurement.update(capture_point="acoustic_output",calibration=proof(),max_clock_error_ms=1,max_capture_error_ms=2)
    for key in ("tool_sha256","detector_sha256","clock_mapping_sha256","noise_threshold_sha256","evidence_window_policy_sha256","cleanup_plan_sha256"): measurement[key] = "3"*64
    for key in campaign["environment"]:
        if key != "environment_id": campaign["environment"][key] = "synthetic-test"
    return corpus, campaign


def event_pairs(campaign, corpus):
    by_id = {case["case_id"]:case for case in corpus["cases"]}
    events = []
    for i, plan in enumerate(campaign["attempt_plan"]):
        start = {"event":"start","campaign_sha256":digest(campaign),**plan,
                 "conditions":copy.deepcopy(campaign["strata"][plan["stratum_id"]]),
                 "t_action_ms":100000+i*10000,"clock_id":"clock-fixture"}
        finish = {"event":"finish","campaign_sha256":digest(campaign),"attempt_id":plan["attempt_id"],
                  "outcome":"success","retry_count":0,"t_sound_ms":start["t_action_ms"]+1000,
                  "clock_id":"clock-fixture","onset_kind":"actual_output","target_content_confirmed":True,
                  "measurement_id":campaign["measurement"]["measurement_id"],"calibration_sha256":"1"*64,
                  "end_conditions":copy.deepcopy(start["conditions"]),
                  "final_source":by_id[plan["case_id"]]["source"],"evidence":proof()}
        events += [start,finish]
    return events


def chained(events):
    result, previous = [], ZERO
    for i, event in enumerate(events):
        row = {**event,"sequence":i+1,"previous_sha256":previous}
        result.append(row); previous = digest(row)
    return result


class CorpusContracts(unittest.TestCase):
    def test_real_draft_is_not_playable_evidence(self):
        corpus,campaign=drafts(); result=validate_corpus(corpus)
        self.assertTrue(result["valid"]); self.assertFalse(result["freeze_ready"])
        self.assertEqual(result["summary"]["distinct_candidate_identities"],33)
        self.assertEqual(result["summary"]["media_decoded_identities"],0)
        self.assertEqual(result["summary"]["native_output_submitted_identities"],0)
        self.assertTrue(validate_campaign(campaign,corpus)["valid"])
        self.assertFalse(validate_campaign(campaign,corpus)["freeze_ready"])

    def test_synthetic_complete_contract_is_accepted(self):
        corpus,campaign=fixture()
        self.assertTrue(validate_corpus(corpus)["freeze_ready"])
        self.assertTrue(validate_campaign(campaign,corpus)["freeze_ready"])

    def test_duplicate_source_is_not_another_song(self):
        corpus,_=fixture(); corpus["cases"][1]["source"]=copy.deepcopy(corpus["cases"][0]["source"])
        self.assertIn("duplicate_source_identity",str(validate_corpus(corpus)["errors"]))

    def test_metadata_only_and_no_audition_cannot_freeze(self):
        corpus,_=fixture(); corpus["cases"][0]["checks"]["audibility"]={"state":"unknown","evidence":None}
        self.assertFalse(validate_corpus(corpus)["valid"])

    def test_decoder_and_muted_native_output_never_promote_audibility_or_identity(self):
        corpus,_=drafts();case=corpus["cases"][0];verified,_=fixture()
        for key in ("media_transport","media_decoded","native_output_submitted"):
            case["checks"][key]=copy.deepcopy(verified["cases"][0]["checks"][key])
        case["checks"]["native_output_submitted"].update(muted=True,nonzero_frames=0)
        result=validate_corpus(corpus);self.assertTrue(result["valid"]);self.assertFalse(result["freeze_ready"])
        for key in ("media_transport_observed_identities","media_decoded_identities","native_output_submitted_identities"):
            self.assertEqual(result["summary"][key],1)
        for key in ("metadata_verified_identities","audibly_confirmed_identities","recording_identity_confirmed_identities","freeze_eligible_positives","complete_decode_identities"):
            self.assertEqual(result["summary"][key],0)
        case["checks"]["native_output_submitted"]["nonzero_frames"]=1
        self.assertIn("muted_post_gain_nonzero_conflict",str(validate_corpus(corpus)["errors"]))

    def test_partial_transport_and_decode_keep_explicit_extent_and_observed_format(self):
        corpus,_=fixture();case=corpus["cases"][0]
        case["checks"]["media_transport"].update(extent="initial_segment",expected_bytes=None)
        result=validate_corpus(corpus);self.assertTrue(result["freeze_ready"])
        self.assertEqual(result["summary"]["complete_transport_identities"],32)
        self.assertEqual(result["summary"]["complete_decode_identities"],0)
        case["checks"]["media_transport"]["extent"]="complete"
        self.assertIn("complete_transport_length_unverified",str(validate_corpus(corpus)["errors"]))
        corpus,_=fixture();corpus["cases"][0]["checks"]["media_decoded"]["format"]["codec"]="unknown"
        self.assertIn("invalid_observed_format",str(validate_corpus(corpus)["errors"]))

    def test_failed_stage_needs_evidence_and_legacy_playable_cannot_replace_stages(self):
        corpus,_=drafts();corpus["cases"][0]["checks"]["media_decoded"]["state"]="failed"
        self.assertFalse(validate_corpus(corpus)["valid"])
        corpus["cases"][0]["checks"]["media_decoded"]["evidence"]=proof()
        self.assertTrue(validate_corpus(corpus)["valid"])
        corpus["cases"][0]["checks"]["playback"]={"state":"passed","evidence":proof()}
        self.assertIn("explicit_media_stages_required",str(validate_corpus(corpus)["errors"]))

    def test_missing_metadata_evidence_and_unselected_negative(self):
        corpus,_=fixture(); corpus["cases"][0]["metadata"].pop("evidence")
        self.assertFalse(validate_corpus(corpus)["valid"])
        corpus,_=fixture(); corpus["negative_cases"][0].pop("source_case_id")
        self.assertIn("negative_source_not_selected",str(validate_corpus(corpus)["errors"]))

    def test_coverage_and_relationships_are_required(self):
        corpus,_=fixture(); corpus["relationships"]=[]
        self.assertFalse(validate_corpus(corpus)["freeze_ready"])
        corpus,_=fixture(); corpus["relationships"][0]["automatic_substitution"]=True
        self.assertFalse(validate_corpus(corpus)["valid"])

    def test_malformed_and_sensitive_documents_fail_closed(self):
        for malformed in (None,[],{"schema_version":1,"cookie":"private"},{"visitorData":"private"},{"https://private.example/?token=private":True}):
            with self.subTest(kind=type(malformed).__name__):self.assertFalse(validate_corpus(malformed)["valid"])
        corpus,_=fixture(); corpus["cases"][0]["source"]["page"]+="&signature=fixture"
        self.assertFalse(validate_corpus(corpus)["valid"])


class CampaignContracts(unittest.TestCase):
    def test_hash_and_platform_bindings(self):
        corpus,campaign=fixture(); campaign["corpus_sha256"]="0"*64
        self.assertFalse(validate_campaign(campaign,corpus)["valid"])
        corpus,campaign=fixture(); campaign["platform"]="ios"
        self.assertFalse(validate_campaign(campaign,corpus)["valid"])

    def test_one_hundred_per_build_and_pair_identity(self):
        corpus,campaign=fixture(); campaign["attempt_plan"]=campaign["attempt_plan"][:-2]
        self.assertFalse(validate_campaign(campaign,corpus)["freeze_ready"])
        corpus,campaign=fixture(); campaign["attempt_plan"][1]["case_id"]="C002"
        self.assertIn("unpaired_comparison_plan",str(validate_campaign(campaign,corpus)["errors"]))

    def test_unqualified_silence_and_pre_output_capture(self):
        corpus,campaign=fixture(); corpus["cases"][0]["onset"]["leading_silence_ms"]=251;campaign["corpus_sha256"]=digest(corpus)
        self.assertFalse(validate_campaign(campaign,corpus)["freeze_ready"])
        corpus,campaign=fixture();campaign["measurement"]["capture_point"]="digital_before_hardware"
        self.assertFalse(validate_campaign(campaign,corpus)["freeze_ready"])

    def test_threshold_changes_and_cold_cache_are_not_silent(self):
        corpus,campaign=fixture();campaign["policy"]["thresholds"]["p95_ms"]=6000
        self.assertFalse(validate_campaign(campaign,corpus)["valid"])

    def test_seeded_order_and_calibration_are_fixed_before_execution(self):
        corpus,campaign=fixture();campaign["policy"]["random_seed"]+=1
        self.assertIn("seeded_schedule_mismatch",str(validate_campaign(campaign,corpus)["errors"]))
        corpus,campaign=fixture();campaign["measurement"]["calibration"]["observed_at"]="2026-11-11T00:00:00Z"
        self.assertIn("calibration_after_freeze",str(validate_campaign(campaign,corpus)["errors"]))
        corpus,campaign=fixture();campaign["strata"]["main_cold"]["media"]="complete_cache"
        self.assertFalse(validate_campaign(campaign,corpus)["valid"])


class StatisticsContracts(unittest.TestCase):
    def setUp(self):
        self.corpus,self.campaign=fixture();self.events=event_pairs(self.campaign,self.corpus)

    def result(self):return summarize(self.campaign,self.corpus,chained(self.events))

    def test_complete_synthetic_run_and_nearest_rank(self):
        result=self.result();self.assertTrue(result["performance_conclusion_allowed"])
        self.assertEqual(result["planned"],200)
        self.assertTrue(all(g["p95_ms"]==1000 for g in result["groups"]))
        self.assertEqual(nearest_rank([1,2,3,4],.5),2)
        self.assertEqual(nearest_rank([1,2,float("inf")],.95),"infinity")

    def test_missing_sound_and_file_loaded_never_count(self):
        self.events[1].pop("t_sound_ms"); self.events[1]["t_file_loaded_ms"]=101000
        result=self.result();self.assertFalse(result["performance_conclusion_allowed"])
        baseline=next(g for g in result["groups"] if g["build_id"]=="baseline063")
        self.assertEqual(baseline["successes"],99);self.assertEqual(baseline["outcomes"]["unverified_sound"],1)
        self.events[1]["t_sound_ms"]=101000; self.events[1]["onset_kind"]="file_loaded"
        self.assertFalse(self.result()["performance_conclusion_allowed"])

    def test_all_failures_and_cancellations_stay_in_denominator(self):
        failures=["player_error","source_rejected","source_changed","network_error","timeout","wrong_recording","cancelled","manual_intervention"]
        changed=0
        for event in self.events:
            if event["event"]=="finish" and event["attempt_id"].startswith("baseline063") and changed<len(failures):
                event["outcome"]=failures[changed];event.pop("t_sound_ms");changed+=1
        result=self.result();baseline=next(g for g in result["groups"] if g["build_id"]=="baseline063")
        self.assertEqual(baseline["started"],100);self.assertEqual(baseline["success_rate_all_started"],.92)
        self.assertEqual(baseline["p95_ms"],"infinity");self.assertEqual(baseline["successful_only_p95_ms"],1000)
        self.assertTrue(result["performance_conclusion_allowed"])
        self.assertFalse(next(x for x in result["comparison"] if x["build_id"]=="baseline063")["observed_thresholds_met"])

    def test_incomplete_and_not_started_remain_visible(self):
        self.events=self.events[:-3];result=self.result()
        self.assertFalse(result["performance_conclusion_allowed"])
        self.assertEqual(len(result["not_started_attempt_ids"]),1)
        self.assertEqual(sum(g["outcomes"].get("unfinished",0) for g in result["groups"]),1)

    def test_reordered_completed_attempts_are_retained_but_not_comparable(self):
        self.events[:4]=self.events[2:4]+self.events[:2]
        result=self.result();self.assertFalse(result["performance_conclusion_allowed"])
        self.assertIn("actual_start_order_differs_from_frozen_plan",str(result["issues"]))
        self.assertEqual(result["started"],200);self.assertEqual(result["journal_events"],400)
        self.assertEqual(sum(g["successes"] for g in result["groups"]),200)
        self.assertEqual(result["actual_base_start_order"][0],self.campaign["attempt_plan"][1]["attempt_id"])

    def test_overlapping_attempts_and_unfinished_predecessor_are_retained(self):
        self.events[1],self.events[2]=self.events[2],self.events[1]
        result=self.result();self.assertFalse(result["performance_conclusion_allowed"])
        self.assertIn("overlapping_attempts",str(result["issues"]))
        self.assertEqual(result["started"],200);self.assertEqual(result["unfinished_attempt_ids"],[])
        self.events=event_pairs(self.campaign,self.corpus);missing=self.events.pop(1)["attempt_id"]
        result=self.result();self.assertFalse(result["performance_conclusion_allowed"])
        self.assertIn(missing,result["unfinished_attempt_ids"]);self.assertEqual(result["journal_events"],399)
        self.assertEqual(sum(g["outcomes"].get("unfinished",0) for g in result["groups"]),1)

    def test_hot_or_changed_route_splits_actual_strata(self):
        self.events[0]["conditions"]["media"]="complete_cache"
        result=self.result();self.assertEqual(len(result["groups"]),3)
        self.assertFalse(result["performance_conclusion_allowed"])

    def test_mid_attempt_condition_change_is_not_hidden(self):
        self.events[1]["end_conditions"]["network"]="offline"
        result=self.result();self.assertFalse(result["performance_conclusion_allowed"])
        self.assertIn("conditions_changed_during_attempt",str(result["issues"]))

    def test_real_hot_group_stays_separate(self):
        self.campaign["strata"]["warm"]={**self.campaign["strata"]["main_cold"],"process":"running","media":"complete_cache"}
        for bid in ("baseline063","candidate"):
            self.campaign["attempt_plan"].append({"attempt_id":bid+"-warm","pair_id":"warm-pair","case_id":"C001","build_id":bid,"stratum_id":"warm"})
        self.events=event_pairs(self.campaign,self.corpus);result=self.result()
        self.assertEqual(len(result["groups"]),4);self.assertTrue(result["performance_conclusion_allowed"])
        self.assertEqual(len(result["comparison"]),2)

    def test_retry_clock_and_identity_cannot_reset(self):
        self.events[1].update(retry_count=2,t_sound_ms=103000,t_retry_action_ms=102500)
        result=self.result();baseline=next(g for g in result["groups"] if g["build_id"]=="baseline063")
        self.assertEqual(baseline["attempts"][0]["sound_latency_ms"],3000);self.assertEqual(baseline["retry_count"],2)
        self.events[1]["final_source"]=self.corpus["cases"][1]["source"]
        self.assertFalse(self.result()["performance_conclusion_allowed"])

    def test_measurement_failure_requires_resolution_and_original_remains(self):
        self.events[1].update(outcome="measurement_invalid",measurement_error="capture_failed");self.events[1].pop("t_sound_ms")
        self.assertFalse(self.result()["performance_conclusion_allowed"])
        start=copy.deepcopy(self.events[0]);start.update(attempt_id=start["attempt_id"]+".replacement1",replacement_for=self.events[0]["attempt_id"],t_action_ms=9000000)
        end=copy.deepcopy(event_pairs(self.campaign,self.corpus)[1]);end.update(attempt_id=start["attempt_id"],t_sound_ms=9001000)
        self.events += [start,end];result=self.result()
        self.assertTrue(result["performance_conclusion_allowed"])
        baseline=next(g for g in result["groups"] if g["build_id"]=="baseline063")
        self.assertEqual(baseline["started"],101);self.assertEqual(baseline["measurement_invalid"],1)
        self.assertEqual(baseline["successes"],100)

    def test_measurement_replacement_cannot_reorder_remaining_base_attempts(self):
        self.events[1].update(outcome="measurement_invalid",measurement_error="capture_failed");self.events[1].pop("t_sound_ms")
        start=copy.deepcopy(self.events[0]);start.update(attempt_id=start["attempt_id"]+".replacement1",replacement_for=self.events[0]["attempt_id"],t_action_ms=102000)
        end=copy.deepcopy(event_pairs(self.campaign,self.corpus)[1]);end.update(attempt_id=start["attempt_id"],t_sound_ms=103000)
        self.events[2:2]=[start,end];result=self.result()
        self.assertFalse(result["performance_conclusion_allowed"])
        self.assertIn("replacement_before_base_plan_completed",str(result["issues"]))
        self.assertEqual(result["started"],201);self.assertEqual(result["journal_events"],402)
        self.assertEqual(len(result["invalid_replacements"]),1)

    def test_network_failure_is_not_measurement_invalid(self):
        self.events[1].update(outcome="measurement_invalid",measurement_error="network_error")
        result=self.result();self.assertFalse(result["performance_conclusion_allowed"])
        self.assertIn("invalid_measurement_excuse",str(result["issues"]))

    def test_replacing_a_player_failure_is_forbidden(self):
        self.events[1].update(outcome="timeout")
        start=copy.deepcopy(self.events[0]);start.update(attempt_id=start["attempt_id"]+".replacement1",replacement_for=self.events[0]["attempt_id"])
        self.events.append(start)
        self.assertIn("unplanned_attempt",str(self.result()["issues"]))

    def test_stale_campaign_clock_and_calibration_fail_closed(self):
        for key,value in (("campaign_sha256","f"*64),("clock_id","other-clock"),("calibration_sha256","f"*64)):
            with self.subTest(field=key):
                events=copy.deepcopy(self.events);events[1][key]=value
                self.assertFalse(summarize(self.campaign,self.corpus,chained(events))["performance_conclusion_allowed"])

    def test_duplicate_final_and_tampered_chain(self):
        self.events.append(copy.deepcopy(self.events[1]));self.assertFalse(self.result()["performance_conclusion_allowed"])
        rows=chained(self.events);rows[0]["t_action_ms"]+=1
        self.assertTrue(chain_errors(rows))

    def test_draft_cannot_yield_a_performance_conclusion(self):
        self.campaign["status"]="draft";self.events=event_pairs(self.campaign,self.corpus)
        self.assertFalse(self.result()["performance_conclusion_allowed"])


class JournalIO(unittest.TestCase):
    def test_append_preserves_bytes_and_rejects_chain_rewrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"attempts.jsonl"
            first=append_event(path,{"event":"fixture_start"});before=path.read_bytes()
            second=append_event(path,{"event":"fixture_finish"})
            self.assertTrue(path.read_bytes().startswith(before));self.assertEqual(first["sequence"],1);self.assertEqual(second["sequence"],2)
            self.assertFalse(chain_errors(read_events(path)))
            with self.assertRaises(Invalid):append_event(path,{"sequence":1})

    def test_duplicate_json_keys_and_nan_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            for raw in ('{"status":"frozen","status":"draft"}','{"x":NaN}'):
                path=Path(directory)/"input.json";path.write_text(raw)
                with self.assertRaises(Invalid):read_json(path)
            path.write_text('{"outcome":"timeout","outcome":"success"}\n')
            with self.assertRaises(Invalid):read_events(path)


if __name__ == "__main__":
    owned_temp = Path(os.environ.get("TMPDIR", ""))
    if not owned_temp.is_dir() or not str(owned_temp.resolve()).startswith("/Users/xiaotwu/.muses/tmp/p0-20261110-01/source/macos-corpus"):
        raise SystemExit("Set TMPDIR to the existing owned macos-corpus scratch before running tests.")
    unittest.main(verbosity=2)
