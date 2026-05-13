from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


def _load_first_dossier_with_clinical_and_gmp(api_module) -> dict:
    for dossier in api_module.state["dossiers"]:
        titles = {str(section.get("title", "")).lower() for section in dossier.get("sections", [])}
        if any("gmp" in title or "manufacturer" in title for title in titles) and any(
            "clinical" in title or "trial" in title for title in titles
        ):
            return dossier
    raise AssertionError("No suitable dossier found for quality test")


def _load_first_amr_dossier(api_module) -> dict:
    for dossier in api_module.state["dossiers"]:
        policy = dossier.get("policy_signals", {})
        if policy.get("aware_category") in {"watch", "reserve"}:
            return dossier
    raise AssertionError("No suitable AMR dossier found for quality test")


def test_review_output_is_relevant_grounded_and_actionable(client, api_module):
    dossier = _load_first_dossier_with_clinical_and_gmp(api_module)
    response = client.post(
        "/v1/review",
        json={
            "dossier_id": dossier["dossier_id"],
            "question": "Compare GMP certificate validity with pivotal trial outcome and recommend the next regulatory action with citations.",
            "top_k": 6,
            "model_id": "gemma-e4b",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    rationale = payload["rationale"].lower()
    cited_ids = {citation["citation_id"] for citation in payload["citations"]}

    assert payload["abstained"] is False
    assert payload["verifier"]["passed"] is True
    assert payload["recommendation"] in {"approval_granted", "approval_denied", "additional_information_required", "abstain"}
    assert "recommendation" in rationale
    assert "gmp" in rationale
    assert "trial" in rationale or "clinical" in rationale
    assert len(payload["citations"]) >= 2
    assert payload["verifier"]["grounded_claim_rate"] >= 0.95
    assert any("gmp" in citation["section_title"].lower() or "manufacturer" in citation["section_title"].lower() for citation in payload["citations"])
    assert any("clinical" in citation["section_title"].lower() or "trial" in citation["section_title"].lower() for citation in payload["citations"])


def test_review_context_awareness_carries_over_between_linked_chats(client, api_module):
    dossier = _load_first_dossier_with_clinical_and_gmp(api_module)

    first = client.post(
        "/v1/conversations",
        json={"title": "First thread", "dossier_id": dossier["dossier_id"], "model_id": "gemma-e4b"},
    ).json()
    first_response = client.post(
        "/v1/review",
        json={
            "dossier_id": dossier["dossier_id"],
            "question": "Summarize the GMP and clinical posture for this dossier.",
            "conversation_id": first["conversation"]["conversation_id"],
            "model_id": "gemma-e4b",
        },
    )
    assert first_response.status_code == 200

    second = client.post(
        "/v1/conversations",
        json={
            "title": "Linked thread",
            "dossier_id": dossier["dossier_id"],
            "model_id": "gemma-e4b",
            "linked_from_conversation_id": first["conversation"]["conversation_id"],
        },
    )
    assert second.status_code == 200
    second_payload = second.json()
    assert second_payload["conversation"]["linked_from_conversation_id"] == first["conversation"]["conversation_id"]
    assert second_payload["carryover_summary"]

    linked_response = client.post(
        "/v1/review",
        json={
            "dossier_id": dossier["dossier_id"],
            "question": "Continue from the prior discussion and focus on the unresolved regulatory risk.",
            "conversation_id": second_payload["conversation"]["conversation_id"],
            "model_id": "gemma-e4b",
        },
    )
    assert linked_response.status_code == 200
    linked_payload = linked_response.json()
    assert linked_payload["conversation_id"] == second_payload["conversation"]["conversation_id"]
    assert linked_payload["context_monitor"]["used_tokens"] > 0
    assert linked_payload["abstained"] is False
    assert "regulatory" in linked_payload["rationale"].lower() or "risk" in linked_payload["rationale"].lower()
    assert "prior reviewer thread" in linked_payload["rationale"].lower() or "prior discussion" in linked_payload["rationale"].lower()


def test_dossier_schema_and_labels_are_sufficient_for_review_task():
    root = Path(r"d:\projects\ai dossier assistant")
    counts = Counter()
    required_policy = {
        "gmp_inspection_status",
        "gmp_certificate_validity",
        "clinical_data_available",
        "pivotal_trial_outcome",
        "aware_category",
        "amr_unmet_need",
        "glass_resistance_trend",
        "similarity_to_existing_watch",
        "existing_watch_comparator",
    }
    required_labels = {"holistic_policy_decision", "risk_score"}
    sample_size = 120

    with (root / "synthetic_data/data/raw/balanced_v1_2026-04-05/dossiers.jsonl").open("r", encoding="utf-8") as handle:
        for idx, line in enumerate(handle):
            if idx >= sample_size:
                break
            dossier = json.loads(line)
            assert required_policy.issubset(dossier["policy_signals"].keys())
            assert required_labels.issubset(dossier["labels"].keys())
            assert dossier["product"]["inn_name"]
            assert dossier["organization"]["applicant"]
            assert dossier["sections"]
            for section in dossier["sections"]:
                counts[str(section.get("module", ""))] += 1
                assert {"presence", "correctness"}.issubset(section["labels"].keys())
                assert {"min_chars", "max_chars"}.issubset(section["constraints"].keys())
                assert "char_count" in section["metrics"]

    assert counts["1"] > 0
    assert counts["2"] > 0
    assert counts["3"] > 0
    assert counts["4"] > 0
    assert counts["5"] > 0


def test_curated_sample_dossiers_cover_primary_demo_paths():
    root = Path(r"d:\projects\ai dossier assistant")
    sample_dir = root / "sample_dossiers"
    payloads = [json.loads(path.read_text(encoding="utf-8")) for path in sample_dir.glob("*.json")]

    decisions = {payload["labels"]["holistic_policy_decision"] for payload in payloads}
    dossier_ids = {payload["dossier_id"] for payload in payloads}
    demo_text = " ".join(str(payload.get("demo_focus", "")) for payload in payloads).lower()

    assert len(payloads) >= 6
    assert {"standard_review", "fast_track", "deep_review", "reject_and_return", "additional_information_required"}.issubset(decisions)
    assert "UPLOAD-RESERVE-001" in dossier_ids
    assert "UPLOAD-WATCH-001" in dossier_ids
    assert "UPLOAD-STANDARD-001" in dossier_ids
    assert "UPLOAD-REJECT-001" in dossier_ids
    assert "UPLOAD-DEEP-001" in dossier_ids
    assert "UPLOAD-CHEM-001" in dossier_ids
    assert "chemistry" in demo_text
    assert "reject" in demo_text


def test_review_output_changes_with_question_focus(client, api_module):
    dossier_id = _load_first_amr_dossier(api_module)["dossier_id"]

    gmp_response = client.post(
        "/v1/review",
        json={
            "dossier_id": dossier_id,
            "question": "Focus only on GMP and manufacturer quality concerns in this dossier.",
            "top_k": 6,
            "model_id": "gemma-e4b",
        },
    )
    amr_response = client.post(
        "/v1/review",
        json={
            "dossier_id": dossier_id,
            "question": "What are the key AMR stewardship issues in this dossier and why do they matter?",
            "top_k": 6,
            "model_id": "gemma-e4b",
        },
    )

    assert gmp_response.status_code == 200
    assert amr_response.status_code == 200

    gmp_payload = gmp_response.json()
    amr_payload = amr_response.json()
    gmp_rationale = gmp_payload["rationale"].lower()
    amr_rationale = amr_payload["rationale"].lower()

    assert gmp_rationale != amr_rationale
    assert any(
        "gmp" in citation["section_title"].lower() or "manufacturer" in citation["section_title"].lower()
        for citation in gmp_payload["citations"]
    )
    assert (
        "amr" in amr_rationale
        or "stewardship" in amr_rationale
        or any(
            any(term in citation["section_title"].lower() for term in ("amr", "stewardship", "aware", "glass"))
            for citation in amr_payload["citations"]
        )
    )


def test_review_can_count_rank_and_categorize_issues(client, api_module):
    dossier_id = _load_first_amr_dossier(api_module)["dossier_id"]

    count_response = client.post(
        "/v1/review",
        json={"dossier_id": dossier_id, "question": "Count the number of issues identified in this dossier.", "top_k": 6},
    )
    rank_response = client.post(
        "/v1/review",
        json={"dossier_id": dossier_id, "question": "Rank the issues in this dossier by importance.", "top_k": 6},
    )
    categorize_response = client.post(
        "/v1/review",
        json={"dossier_id": dossier_id, "question": "Categorize the issues in this dossier.", "top_k": 6},
    )

    assert count_response.status_code == 200
    assert rank_response.status_code == 200
    assert categorize_response.status_code == 200

    assert "identified" in count_response.json()["rationale"].lower()
    assert rank_response.json()["abstained"] is False
    assert len(rank_response.json()["rationale"].strip()) > 40
    assert len(rank_response.json()["citations"]) >= 1
    assert categorize_response.json()["abstained"] is False
    assert ":" in categorize_response.json()["rationale"] or "category" in categorize_response.json()["rationale"].lower()
    assert count_response.json()["verifier"]["grounded_claim_rate"] >= 0.95


def test_follow_up_issue_questions_do_not_abstain_for_intake_style_dossier(client):
    text = (
        "Manufacturer and GMP Evidence\n\n"
        "GMP certificate remains valid and no critical findings were reported.\n\n"
        "Clinical Overview and Benefit-Risk Summary\n\n"
        "Primary endpoint was met in the pivotal study.\n\n"
        "AMR Stewardship Narrative\n\n"
        "No watch restriction was triggered and no rising resistance signal was identified."
    ).encode("utf-8")
    intake_response = client.post(
        "/v1/dossiers/intake",
        data={
            "dossier_id": "INTAKE-CHAT-CONTINUITY-001",
            "country": "Uganda",
            "submission_date": "2026-04-11",
            "product_name": "Continuity Sample",
            "inn_name": "amoxicillin",
            "applicant": "Continuity Applicant",
            "manufacturer": "Continuity Manufacturer",
            "facility_country": "Uganda",
        },
        files={"file": ("incoming.txt", text, "text/plain")},
    )
    assert intake_response.status_code == 200

    conversation_response = client.post(
        "/v1/conversations",
        json={"title": "Continuity test", "dossier_id": "INTAKE-CHAT-CONTINUITY-001"},
    )
    assert conversation_response.status_code == 200
    conversation_id = conversation_response.json()["conversation"]["conversation_id"]

    first_response = client.post(
        "/v1/review",
        json={
            "dossier_id": "INTAKE-CHAT-CONTINUITY-001",
            "question": "Review this dossier, identify missing or contradictory evidence, explain the key issues, and give a recommendation with citations.",
            "conversation_id": conversation_id,
            "top_k": 6,
        },
    )
    follow_up_response = client.post(
        "/v1/review",
        json={
            "dossier_id": "INTAKE-CHAT-CONTINUITY-001",
            "question": "How many issues have you identified?",
            "conversation_id": conversation_id,
            "top_k": 6,
        },
    )

    assert first_response.status_code == 200
    assert follow_up_response.status_code == 200
    assert follow_up_response.json()["abstained"] is False
    assert "did not identify any material dossier issues" in follow_up_response.json()["rationale"].lower() or "identified" in follow_up_response.json()["rationale"].lower()


def test_review_can_handle_greeting_without_generic_dossier_dump(client, api_module):
    dossier_id = _load_first_amr_dossier(api_module)["dossier_id"]
    response = client.post(
        "/v1/review",
        json={"dossier_id": dossier_id, "question": "Hi friend", "top_k": 6},
    )
    assert response.status_code == 200
    rationale = response.json()["rationale"].lower()
    assert rationale.startswith("hi friend")
    assert "manufacturer and gmp evidence" not in rationale


def test_routine_dossier_questions_do_not_pull_generic_wiki_content(client, api_module):
    dossier_id = _load_first_amr_dossier(api_module)["dossier_id"]
    response = client.post(
        "/v1/review",
        json={
            "dossier_id": dossier_id,
            "question": "What are the key issues in this dossier?",
            "top_k": 6,
        },
    )
    assert response.status_code == 200
    rationale = response.json()["rationale"].lower()
    assert "retrieval-first architecture" not in rationale


def test_review_rationale_reads_cleanly_for_non_greeting_prompt(client, api_module):
    dossier = _load_first_dossier_with_clinical_and_gmp(api_module)
    response = client.post(
        "/v1/review",
        json={
            "dossier_id": dossier["dossier_id"],
            "question": "Summarize the most important review concerns and the next reviewer step.",
            "top_k": 6,
        },
    )
    assert response.status_code == 200
    rationale = response.json()["rationale"]
    lowered = rationale.lower()

    assert "i have analyzed the dossier in response to your request regarding" not in lowered
    assert "based on a comprehensive review of the submitted dossier" not in lowered
    assert "  " not in rationale
    assert ".." not in rationale
    assert "next reviewer step" in lowered
    assert "model switching guidance" not in rationale


def test_amr_rationale_hides_raw_snapshot_artifacts(client, api_module):
    dossier_id = _load_first_amr_dossier(api_module)["dossier_id"]
    response = client.post(
        "/v1/review",
        json={
            "dossier_id": dossier_id,
            "question": "Explain the AMR stewardship concerns and likely authorization controls for this dossier.",
            "top_k": 6,
        },
    )
    assert response.status_code == 200
    rationale = response.json()["rationale"]
    lowered = rationale.lower()
    assert "rxnorm snapshot" not in lowered
    assert "who aware snapshot" not in lowered
    assert "who glass snapshot" not in lowered
    assert "chemistry snapshot" not in lowered
    assert "source_trace" not in lowered


def test_review_can_answer_rule_identification_and_workflow_completeness(client, api_module):
    dossier_id = _load_first_amr_dossier(api_module)["dossier_id"]

    rules_response = client.post(
        "/v1/review",
        json={
            "dossier_id": dossier_id,
            "question": "Identify the applicable review rules, naming rules, product-type rules, and AMR stewardship rules that apply to this dossier.",
            "top_k": 6,
        },
    )
    completeness_response = client.post(
        "/v1/review",
        json={
            "dossier_id": dossier_id,
            "question": "Confirm whether all mandatory workflow steps have been completed, including INN similarity review and AMR stewardship where relevant.",
            "top_k": 6,
        },
    )

    assert rules_response.status_code == 200
    assert completeness_response.status_code == 200
    assert rules_response.json()["abstained"] is False
    assert completeness_response.json()["abstained"] is False
    assert "applicable rules" in rules_response.json()["rationale"].lower()
    assert "review complete" in completeness_response.json()["rationale"].lower() or "review incomplete" in completeness_response.json()["rationale"].lower()
