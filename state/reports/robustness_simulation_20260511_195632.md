# Review Robustness Simulation Report

- Report ID: `robustness_simulation_20260511_195632`
- Executed At (UTC): `2026-05-11T19:58:15.651008`
- Passed: `10` / `10`
- Failed: `0`

## Scenario Results

### S1 - greeting_and_naturalness
- Prompt: `hi fried`
- Dossier: `None`
- Passed: `True`
- Recommendation: `None`
- Route: `chat_only`
- Citations: `0`
- Notes: Expected a natural greeting response rather than dossier-heavy content.
- Response excerpt:

```text
Hi friend. I am ready to assist. You can ask for dossier review, issue discovery, policy guidance, AMR stewardship analysis, or a report-focused summary.
```

### S2 - typo_issue_discovery
- Prompt: `identfy key isues and contrdictions in this dossir`
- Dossier: `SIM-WATCH-20260511_195632`
- Passed: `True`
- Recommendation: `additional_information_required`
- Route: `fallback`
- Citations: `3`
- Notes: Expected typo-tolerant issue discovery with citations.
- Response excerpt:

```text
### Data Quality Check (Mandatory Step 1)

- Status: completed
- OCR/Vision used: no
- Pages analyzed: 7
- Image-heavy pages: 0

### Final Answer

### Executive Summary

The current grounded regulatory recommendation is **Additional Information Required**. The submission covers the product **Watch Review Demo** (levofloxacin), submitted by **Demo Applicant**. The structured review found **2** unre
```

### S3 - query_expansion_stability
- Prompt: `review stablity snd shelf lif justifcation`
- Dossier: `SIM-STANDARD-20260511_195632`
- Passed: `True`
- Recommendation: `approval_granted`
- Route: `fallback`
- Citations: `7`
- Notes: Expected stability-oriented retrieval despite typos.
- Response excerpt:

```text
### Data Quality Check (Mandatory Step 1)

- Status: completed
- OCR/Vision used: no
- Pages analyzed: 7
- Image-heavy pages: 0

### Final Answer

### Executive Summary

The current grounded regulatory recommendation is **Approval Granted**. The submission covers the product **Standard Review Demo** (nitrofurantoin), submitted by **Demo Applicant**. The structured review found **1** unresolved req
```

### S4 - reranking_specificity
- Prompt: `focus on gmp cert expirry, not clinical`
- Dossier: `SIM-SCANNED-20260511_195632`
- Passed: `True`
- Recommendation: `additional_information_required`
- Route: `fallback`
- Citations: `2`
- Notes: Expected GMP-specific evidence to outrank unrelated clinical material.
- Response excerpt:

```text
### Data Quality Check (Mandatory Step 1)

- Status: completed
- OCR/Vision used: yes
- Pages analyzed: 2
- Image-heavy pages: 2
- Scan signals detected: scanned GMP certificate, low-resolution stability table

### Final Answer

### Executive Summary

The current grounded regulatory recommendation is **Additional Information Required**. The submission covers the product **Scanned Review Demo** (le
```

### S5 - ambiguous_followup
- Prompt: `so can we move ahead with this one?`
- Dossier: `SIM-WATCH-20260511_195632`
- Passed: `True`
- Recommendation: `additional_information_required`
- Route: `fallback`
- Citations: `4`
- Notes: Expected the assistant to resolve the ambiguous follow-up using conversation context.
- Response excerpt:

```text
### Final Answer

### Executive Summary

The current grounded regulatory recommendation is **Additional Information Required**. The submission covers the product **Watch Review Demo** (levofloxacin), submitted by **Demo Applicant**. The structured review found **2** unresolved requirement-level concerns.

**AMR Stewardship Analysis:** The product is classified under the **WATCH** category. Watch-c
```

### S6 - guidance_and_mcp_routing
- Prompt: `what reviwer guidnce and who aware poicy applies here?`
- Dossier: `SIM-WATCH-20260511_195632`
- Passed: `True`
- Recommendation: `additional_information_required`
- Route: `fallback`
- Citations: `8`
- Notes: Expected routed guidance response using the unified assistant path.
- Response excerpt:

```text
### SOP Item In Review

- AMR stewardship review using AWaRe rules

### Final Answer

### Executive Summary

The current grounded regulatory recommendation is **Additional Information Required**. The submission covers the product **Watch Review Demo** (levofloxacin), submitted by **Demo Applicant**. The structured review found **2** unresolved requirement-level concerns.

### Naming Policy Complia
```

### S7 - amr_stewardship_decision
- Prompt: `does this require restricted authoriztion and why?`
- Dossier: `SIM-WATCH-20260511_195632`
- Passed: `True`
- Recommendation: `additional_information_required`
- Route: `fallback`
- Citations: `2`
- Notes: Expected stewardship reasoning and authorization-control output.
- Response excerpt:

```text
### Final Answer

### Executive Summary

The current grounded regulatory recommendation is **Additional Information Required**. The submission covers the product **Watch Review Demo** (levofloxacin), submitted by **Demo Applicant**. The structured review found **2** unresolved requirement-level concerns.

**AMR Stewardship Analysis:** The product is classified under the **WATCH** category. Watch-c
```

### S8 - hallucination_resistance
- Prompt: `what exact humidity was the storage room set to?`
- Dossier: `SIM-STANDARD-20260511_195632`
- Passed: `True`
- Recommendation: `abstain`
- Route: `fallback`
- Citations: `0`
- Notes: Expected abstention or explicit silence when the dossier does not provide the requested fact.
- Response excerpt:

```text
### Data Quality Check (Mandatory Step 1)

- Status: completed
- OCR/Vision used: no
- Pages analyzed: 7
- Image-heavy pages: 0

Abstained because no evidence chunks were retrieved for the request.

### Decision Support Snapshot

| Signal | Value |
| --- | --- |
| Recommendation | abstain |
| Confidence | 0.00 |
| Submission Type | pre_market_authorization |


### Safety & Trust: Verdict Trace

- 
```

### S9 - user_error_wrong_dossier
- Prompt: `summarize dossier`
- Dossier: `DOS-NOT-REAL`
- Passed: `True`
- Recommendation: `None`
- Route: `None`
- Citations: `0`
- Notes: Expected a graceful not-found response for an invalid dossier id.
- Response excerpt:

```text
{"detail":"Dossier DOS-NOT-REAL not found"}
```

### S10 - chain_of_thought_pipeline
- Prompt: `review this dossier, identify missing or contradictory evidence, explain the key issues, and give a recommendation with citations.`
- Dossier: `SIM-SCANNED-20260511_195632`
- Passed: `True`
- Recommendation: `additional_information_required`
- Route: `fallback`
- Citations: `2`
- Notes: Expected reasoning trace, final recommendation, and citations in the end-to-end pipeline.
- Response excerpt:

```text
### Data Quality Check (Mandatory Step 1)

- Status: completed
- OCR/Vision used: yes
- Pages analyzed: 2
- Image-heavy pages: 2
- Scan signals detected: scanned GMP certificate, low-resolution stability table

### Final Answer

### Executive Summary

The current grounded regulatory recommendation is **Additional Information Required**. The submission covers the product **Scanned Review Demo** (le
```

## Final Review Report

- Dossier: `SIM-SCANNED-20260511_195632`
- HTML: `/v1/reports/report-cfce0e0543e9/html`
- TXT: `/v1/reports/report-cfce0e0543e9/text`
- JSON: `/v1/reports/report-cfce0e0543e9/json`
