from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from regulatory_mcp_server.schemas import (
    AWaReResult,
    DossierSection,
    Finding,
    SimilarityResult,
    ToolAuditRecord,
    ToolEnvelope,
)


def test_dossier_section_requires_core_fields():
    section = DossierSection(
        section_id="pil-1",
        section_type="patient_information_leaflet",
        title="Patient Information Leaflet",
        text="Use exactly as directed.",
    )
    assert section.section_id == "pil-1"


def test_invalid_similarity_result_fails_cleanly():
    with pytest.raises(ValidationError) as excinfo:
        SimilarityResult(
            proposed_name="Paracare",
            best_match_inn="paracetamol",
            similarity_index=82.1,
            similarity_type=["orthographic"],
            rule_result="blocked",
            decision_effect="cannot_accept_until_resolved",
        )
    assert excinfo.value.errors()[0]["type"] == "literal_error"


def test_invalid_aware_category_fails_cleanly():
    with pytest.raises(ValidationError) as excinfo:
        AWaReResult(
            active_ingredient="amoxicillin",
            is_antimicrobial=True,
            aware_category="access",
            reserve_related=False,
            source="cached_fixture",
            source_date="2026-04-25",
        )
    assert excinfo.value.errors()[0]["loc"] == ("aware_category",)


def test_tool_envelope_contains_audit_contract():
    envelope = ToolEnvelope(
        status="success",
        data={"status": "ok"},
        warnings=[],
        source_refs=[],
        audit=ToolAuditRecord(
            tool_name="health_status",
            timestamp=datetime.now(timezone.utc),
            request_id="req-1",
            input_hash="abc123",
        ),
    )
    assert envelope.audit.tool_name == "health_status"
    assert envelope.status == "success"


def test_finding_severity_is_validated():
    with pytest.raises(ValidationError):
        Finding(
            review_area="gmp",
            finding="Certificate expired",
            severity="blocker",
            violated_rule="Expired GMP certificate",
            evidence_ref="DOS-1:m1_gmp",
            recommendation="Renew the certificate.",
        )

