from __future__ import annotations

import pytest
from fastapi import HTTPException


def _any_dossier(api_module):
    dossier_id = next(iter(api_module.state["dossier_by_id"].keys()))
    dossier = api_module.state["dossier_by_id"][dossier_id]
    return dossier_id, dossier


def test_strict_step_marker_blocks_jump_ahead_on_first_turn(api_module):
    dossier_id, dossier = _any_dossier(api_module)
    conversation_id = "conv-seq-jump"
    api_module.state["workflow_progress"][f"{conversation_id}::{dossier_id}"] = api_module._new_workflow_progress(
        dossier_id=dossier_id,
        conversation_id=conversation_id,
    )

    with pytest.raises(HTTPException) as exc:
        api_module._workflow_sequence_gate(
            dossier=dossier,
            question="[SOP Step 3] sop_step_id::administrative_completeness_review Run administrative completeness checks.",
            conversation_id=conversation_id,
        )

    assert exc.value.status_code == 409
    detail = exc.value.detail
    assert detail["requested_step"] == "administrative_completeness_review"
    assert detail["next_required_step"] == "data_quality_and_vision_extraction_check"


def test_strict_step_marker_allows_only_next_required_step(api_module):
    dossier_id, dossier = _any_dossier(api_module)
    conversation_id = "conv-seq-ordered"
    progress = api_module._new_workflow_progress(
        dossier_id=dossier_id,
        conversation_id=conversation_id,
    )
    api_module.state["workflow_progress"][f"{conversation_id}::{dossier_id}"] = progress

    # Step 1 should be permitted.
    api_module._workflow_sequence_gate(
        dossier=dossier,
        question="[SOP Step 1] sop_step_id::data_quality_and_vision_extraction_check Run data quality checks.",
        conversation_id=conversation_id,
    )

    # Simulate step 1 completion, then step 2 should be permitted.
    progress["completed_steps"] = {"data_quality_and_vision_extraction_check"}
    api_module.state["workflow_progress"][f"{conversation_id}::{dossier_id}"] = progress
    api_module._workflow_sequence_gate(
        dossier=dossier,
        question="[SOP Step 2] sop_step_id::submission_intake_and_familiarization Run intake and familiarization.",
        conversation_id=conversation_id,
    )

