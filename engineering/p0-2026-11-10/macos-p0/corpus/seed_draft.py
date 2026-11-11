#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Author the reviewed candidate list; never fetches or marks playback verified.

Writes only named draft files into an explicitly supplied directory, refusing
overwrite. Run through the P0 source allocation guard. No third-party payloads.
"""
import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
from campaign import balanced_plan, digest

CHECKED_ON = "2026-11-10"
# Metadata observations are page titles/catalog entries, not availability tests.
# id, title, artist, languages, kind, proposed version, metadata observation
ROWS = [
    ("YQHsXMglC9A", "Hello", "Adele", ["latin"], "music_video", "studio_music_video", "page_title_observed"),
    ("mHONNcZbwDY", "Hello", "Lionel Richie", ["latin"], "music_video", "studio_music_video", "catalog_observed"),
    ("kTJczUoc26U", "STAY", "The Kid LAROI, Justin Bieber", ["latin"], "music_video", "studio_music_video", "page_title_observed"),
    ("JF8BRvqGCNs", "Stay", "Rihanna, Mikky Ekko", ["latin"], "music_video", "studio_music_video", "page_title_observed"),
    ("y8AWFf7EAc4", "Hallelujah", "Jeff Buckley", ["latin"], "live_video", "Live at Bearsville", "page_title_observed"),
    ("YrLk4vdY28Q", "Hallelujah", "Leonard Cohen", ["latin"], "live_video", "Live in London 2008", "page_title_observed"),
    ("djV11Xbc914", "Take On Me", "a-ha", ["latin"], "music_video", "Official Video 4K", "page_title_observed"),
    ("HzdD8kbDzZA", "Take on Me", "a-ha", ["latin"], "audio", "Hunting High and Low", "catalog_observed"),
    ("92SGEe8l2Ng", "Take On Me (MTV Unplugged)", "a-ha", ["latin"], "audio", "MTV Unplugged - Summer Solstice", "catalog_observed"),
    ("jg5mXCCbd0U", "Take On Me (MTV Unplugged / Edit)", "a-ha", ["latin"], "audio", "MTV Unplugged edit", "catalog_observed"),
    ("4D7u5KF7SP8", "Get Lucky (feat. Pharrell Williams and Nile Rodgers)", "Daft Punk", ["latin"], "audio", "Random Access Memories", "catalog_observed"),
    ("Rgrt_8mXrK8", "Get Lucky (Radio Edit - feat. Pharrell Williams and Nile Rodgers)", "Daft Punk", ["latin"], "audio", "radio_edit", "catalog_observed"),
    ("NnC2MtBSdsg", "Get Lucky (Daft Punk Remix)", "Daft Punk", ["latin"], "audio", "remix", "catalog_observed"),
    ("5NV6Rdv1a3I", "Get Lucky (Official Audio) ft. Pharrell Williams, Nile Rodgers", "Daft Punk", ["latin"], "audio", "unknown", "page_title_observed"),
    ("SX_ViT4Ra7k", "Lemon", "米津玄師 Kenshi Yonezu", ["ja", "latin"], "music_video", "studio_music_video", "page_title_observed"),
    ("ZRtdQ81jPUQ", "アイドル", "YOASOBI", ["ja", "latin"], "music_video", "studio_music_video", "page_title_observed"),
    ("x8VYWazR5mE", "夜に駆ける", "YOASOBI", ["ja", "latin"], "music_video", "studio_music_video", "page_title_observed"),
    ("4DxL6IKmXx4", "炎", "LiSA", ["ja", "latin"], "music_video", "unknown", "unknown"),
    ("Qp3b-RXtz4w", "うっせぇわ", "Ado", ["ja", "latin"], "music_video", "studio_music_video", "page_title_observed"),
    ("HsuGYhLsKyo", "プリマドンナ", "Roselia", ["ja", "latin"], "unknown", "unknown", "unknown"),
    ("sHD_z90ZKV0", "稻香 Rice Field", "周杰倫 Jay Chou", ["zh", "latin"], "music_video", "studio_music_video", "catalog_observed"),
    ("bu7nU9Mhpyo", "告白氣球 Love Confession", "周杰倫 Jay Chou", ["zh", "latin"], "music_video", "studio_music_video", "catalog_observed"),
    ("_sQSXwdtxlY", "小幸運 A Little Happiness", "田馥甄 Hebe Tien", ["zh", "latin"], "music_video", "Our Times movie-theme MV", "catalog_observed"),
    ("YD9r_tTtlaA", "小幸運 (我的少女時代電影主題曲)", "田馥甄", ["zh"], "audio", "movie_theme_audio", "catalog_observed"),
    ("T4SimnaiktU", "光年之外", "G.E.M. 鄧紫棋", ["zh", "latin"], "music_video", "unknown", "unknown"),
    ("jvqFAi7vkBc", "Sam Altman: OpenAI, GPT-5, Sora, Board Saga, Elon Musk, Ilya, Power & AGI | #419", "Lex Fridman", ["latin"], "podcast", "full_episode_419", "catalog_observed"),
    ("JN3KPFbWCy8", "Elon Musk: War, AI, Aliens, Politics, Physics, Video Games, and Humanity | #400", "Lex Fridman", ["latin"], "podcast", "full_episode_400", "catalog_observed"),
    ("aqz-KE-bpKQ", "Big Buck Bunny", "Blender Foundation", ["latin"], "film", "unknown", "unknown"),
    ("eRsGyueVLvQ", "Sintel", "Blender Foundation", ["latin"], "film", "unknown", "unknown"),
    ("JGwWNGJdvx8", "Shape of You", "Ed Sheeran", ["latin"], "music_video", "studio_music_video", "page_title_observed"),
    ("dQw4w9WgXcQ", "Never Gonna Give You Up", "Rick Astley", ["latin"], "music_video", "unknown", "unknown"),
    ("fJ9rUzIMcZQ", "Bohemian Rhapsody", "Queen", ["latin"], "music_video", "Official Video Remastered", "page_title_observed"),
    ("Zi_XLOBDo_Y", "Billie Jean", "Michael Jackson", ["latin"], "music_video", "studio_music_video", "page_title_observed"),
]


def drafts():
    cases = []
    for index, (sid, title, artist, languages, kind, version, state) in enumerate(ROWS, 1):
        tags = ["unicode_punctuation"] if index in (3, 7, 9, 10, 15, 16, 19, 23, 24, 26) else []
        if len(languages) > 1: tags.append("mixed_script")
        if kind == "podcast": tags.extend(["long_content", "chaptered_podcast"])
        else: tags.append("short_content_candidate")
        page = "https://www.youtube.com/watch?v=" + sid
        reference = "https://lexfridman.com/sam-altman-2/" if index == 26 else "https://lexfridman.com/elon-musk-4/" if index == 27 else page
        notes = "Public page title/catalog only; duration, playable identity and audible onset unverified."
        if index in (18, 20): notes = "Public page fetch throttled; proposed identity remains unknown. No repeated request or access bypass."
        if index == 25: notes = "Public page fetch failed; proposed identity remains unknown."
        if index == 31: notes = "Corrected an initially mistyped 10-character ID; the proper 11-character candidate still needs metadata verification."
        if index in (28, 29): notes = "Existing P0 source-v2 complete-transfer/decode evidence is separate; no present corpus audition or onset measurement."
        if kind == "podcast": notes = "Publisher page links exact YouTube embed and chapter headings beyond one hour. Total duration and audible onset unverified."
        cases.append({"case_id":f"C{index:03d}", "role":"candidate",
            "source":{"provider":"youtube", "id":sid, "page":page},
            "metadata":{"title":title,"artist":artist,"duration_ms":None,"media_kind":kind,"state":state,
                        "checked_on":CHECKED_ON,"reference":reference,"notes":notes},
            "languages":languages,"tags":tags,"recording":"unknown","version":version,
            "account_condition":"anonymous_public_unverified","region_condition":"unknown",
            "retention_policy":"stable_metadata_only; no media captured in this task",
            "checks":{
                "media_transport":{"state":"unknown","extent":"unknown","received_bytes":None,"expected_bytes":None,"evidence":None},
                "media_decoded":{"state":"unknown","extent":"unknown","decoded_frames":None,"format":None,"evidence":None},
                "native_output_submitted":{"state":"unknown","decoded_frames_consumed":None,"submitted_frames":None,"nonzero_frames":None,"muted":None,"evidence":None},
                "audibility":{"state":"unknown","evidence":None},
                "recording_identity":{"state":"unknown","evidence":None}},
            "onset":{"state":"unknown","leading_silence_ms":None,"evidence":None},
            "capabilities":{"state":"unknown","formats":[],"sample_rates_hz":[],"offline_save":"unknown","evidence":None}})
    relationships = []
    for rid, kind, members, variants, note in [
        ("same-hello","same_title",["C001","C002"],[],"Different artists; distinct recordings proposed; never replace by normalized title."),
        ("same-stay","same_title",["C003","C004"],[],"Case-normalized title collision; distinct artist recordings proposed."),
        ("same-hallelujah","same_title",["C005","C006"],[],"Different artists/live performances; do not reuse progress or lyric timing."),
        ("versions-take-on-me","version_family",["C008","C009","C010"],["studio","live","radio_edit"],"Studio, unplugged and edited unplugged labels observed; timeline/precise edit relation still unreviewed."),
        ("versions-get-lucky","version_family",["C011","C012","C013"],["original","radio_edit","remix"],"Album, radio edit and artist remix labels observed; actual recording relation unreviewed."),
        ("mv-audio-take-on-me","mv_audio",["C007","C008"],[],"Independent video/audio IDs; intro/edit equivalence unknown; never transfer timeline automatically."),
        ("mv-audio-little-happiness","mv_audio",["C023","C024"],[],"Movie MV and official audio IDs; possible dialogue/intro differences unmeasured."),
    ]:
        relationships.append({"relation_id":rid,"kind":kind,"members":members,"variants":variants,
            "state":"proposed","timeline_equivalent":"unknown","automatic_substitution":False,"evidence":None,"note":note})
    negatives = [
        {"case_id":"N001","kind":"removed_or_nonexistent","source_id":None,"state":"unknown","expected_error":"source_unavailable","recovery":"Preserve occurrence and explicit unavailable state; no automatic recording replacement.","selection_gap":"Select a reproducibly absent public ID; no invented assertion that an arbitrary ID is absent.","evidence":None},
        {"case_id":"N002","kind":"authorization_required","source_id":None,"state":"unknown","expected_error":"authorization_required","recovery":"Stop and present account requirement; do not fetch cookies or silently switch account scope.","selection_gap":"Need an authorized test-owned or publicly documented restricted identity; do not inspect user account.","evidence":None},
        {"case_id":"N003","kind":"region_or_account_restricted","source_id":None,"state":"unknown","expected_error":"capability_restricted","recovery":"Preserve explicit unsupported reason; no regional bypass or automatic alternate recording.","selection_gap":"Actual restriction and environment need a bounded receipt; not yet selected.","evidence":None},
        {"case_id":"N004","kind":"expired_resolution","source_case_id":"C028","state":"unknown","expected_error":"resolution_expired","recovery":"Re-resolve the same identity once under the original action deadline; never retain the signed URL.","selection_gap":"Use an owned injected-expiry fixture and separately label it synthetic; live expiry unverified.","evidence":None},
        {"case_id":"N005","kind":"invalid_cache","source_case_id":"C028","state":"unknown","expected_error":"cache_invalid","recovery":"Quarantine only the task-owned corrupt cache, keep identity and bounded retry; do not alter user downloads.","selection_gap":"Owned corrupt-cache fixture not yet produced; no production cache operation.","evidence":None},
    ]
    corpus = {"schema_version":1,"corpus_id":"macos-p0-candidates-v1","status":"draft","created_on":CHECKED_ON,
        "owner":"muses-p0","frozen_at":None,"reviewer":None,"cases":cases,"relationships":relationships,
        "negative_cases":negatives,"queue_context":{"state":"proposed","evidence":None,
            "collection":["C001","C003","C001","N001","C004"],"up_next":["C001","C023"],
            "start_collection_index":1,"operations":["next","previous","skip_unavailable"],
            "note":"Each occurrence needs its own queue ID; repeated identity does not count toward 30."},
        "open_coverage_gaps":["All actual playable/audible recording checks and durations remain unknown.",
            "At least 30 main-group entries need measured natural silence <=250ms; keep longer-silence entries in a separate stratum.",
            "Actual AAC/Opus capability and at least two sample rates need independent observation.",
            "Short-duration selection and exact long-podcast duration/chapter labels need verification.",
            "Negative IDs/conditions and queue behavior are planned, not verified.",
            "Mixed-script and same-title cases are proposed; all relationship reviews remain outstanding."]}
    conditions = {"process":"new","resolution":"miss","media":"none","prefetch":"none","connection":"unknown",
        "metadata":"unknown","os_cache":"unknown","account":"anonymous_public","network":"reference",
        "route":"builtin-speakers","sample_rate_hz":48000,"app_volume":0.25,"muted":False,"foreground":"active",
        "environment_id":"macos-p0-unfrozen","measurement_id":"output-capture-unfrozen"}
    main_ids = [c["case_id"] for c in cases[:30]]
    # Draft order only. Seed and deterministic assignment are explicit; there is
    # no claim that these unqualified cases already form a valid main group.
    plan = balanced_plan(main_ids, "baseline063", "candidate", 100, 20261110)
    measurement = {"measurement_id":"output-capture-unfrozen","capture_point":"unknown","calibration":None,
        **{key:None for key in ("tool_sha256","detector_sha256","clock_mapping_sha256","noise_threshold_sha256",
            "evidence_window_policy_sha256","cleanup_plan_sha256","max_clock_error_ms","max_capture_error_ms")}}
    campaign = {"schema_version":1,"protocol_version":1,"campaign_id":"macos-p0-baseline-draft-v1","status":"draft",
        "platform":"macos","corpus_sha256":digest(corpus),"frozen_at":None,"reviewer":None,
        "builds":{
            "baseline063":{"role":"baseline","version":"0.6.3","source_revision":"12260f050a374ee949053e8f63b039fe20f15148",
                "artifact_sha256":"192b4297c6dac82c5115afb1ba7168bae4e88985959a5852f85344df8b9b5a44",
                "executable_sha256":"efb7398d007155d23367f7f87e4c4c9b78748b3d95110d5ef91c2fca6ade7c39",
                "dependencies_sha256":None,"measurement_patch_sha256":None,"signature_verified":False,
                "restrictions":"arm64/macOS26+, official original zip only; isolated measurement derivative not yet frozen"},
            "candidate":{"role":"candidate","version":"unknown","source_revision":None,"artifact_sha256":None,
                "executable_sha256":None,"dependencies_sha256":None,"measurement_patch_sha256":None,"signature_verified":False,"restrictions":None}},
        "environment":{"environment_id":"macos-p0-unfrozen","hardware_alias":"unknown","os_version":"unknown","os_build":"unknown","sdk":"unknown","compiler":"unknown",
            "route_alias":"unknown","capture_chain":"unknown","network_observation":"unknown","isolation_policy":"unknown"},
        "measurement":measurement,"strata":{"main_cold":conditions},
        "policy":{"quantile":"nearest_rank","no_sound":"infinity","invalid_replacement":"append_once_same_plan_conditions",
            "retry_clock":"original_action","thresholds":{"p50_ms":2500,"p95_ms":5000,"success_rate":0.99},
            "timeout_ms":30000,"random_seed":20261110,"interleave_algorithm":"balanced-shuffle-v1-paired-abba",
            "scratch_limit_bytes":128*1024*1024,"free_floor_bytes":40*1024*1024*1024},"attempt_plan":plan}
    return corpus, campaign


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("output_directory");args=parser.parse_args()
    output=Path(args.output_directory);output.mkdir(parents=True,exist_ok=True)
    corpus,campaign=drafts()
    for name,value in (("corpus.draft.json",corpus),("campaign.draft.json",campaign)):
        with (output/name).open("x") as stream:json.dump(value,stream,ensure_ascii=False,indent=2);stream.write("\n")
    print(json.dumps({"status":"draft","candidate_identities":len(corpus["cases"]),"media_decoded":0,"native_output_submitted":0,"audibly_confirmed":0,"media_downloaded":False,"attempts_planned_not_run":len(campaign["attempt_plan"])}))


if __name__=="__main__":main()
