# MCP Realistic Simulation Report

- Generated: 2026-05-07T09:26:25.566381+00:00
- Passed: 5/5
- Failed: 0

## generic_paracetamol_reference_review

- Passed: True
- Summary: Generic patient-information comparison and INN review completed.
- innovator_reference: Panadol
- overall_alignment: not_aligned
- inn_decision_effect: can_continue

## antimicrobial_watch_caution

- Passed: True
- Summary: AWaRe classification and stewardship flag computed.
- aware_category: Watch
- stewardship_flag: review_required

## incorrect_section_example_comparison

- Passed: True
- Summary: Incorrect section comparison produced deterministic findings.
- classification: non_compliant

## chat_chart_and_markdown_table_routing

- Passed: True
- Summary: Chart request and findings tables rendered through the app.
- chart_type: pie
- review_recommendation: additional_information_required

## external_source_supported_answer_trace

- Passed: True
- Summary: External-source-backed cache trace was preserved in the MCP envelope.
- source_type: cache
- audit_tool: fetch_innovator_patient_information
