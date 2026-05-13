# Review Robustness Simulation Report

- Report ID: `robustness_simulation_20260417_213706`
- Executed At (UTC): `2026-04-17T21:38:29.337624`
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
- Dossier: `SIM-WATCH-20260417_213706`
- Passed: `True`
- Recommendation: `additional_information_required`
- Route: `fallback`
- Citations: `3`
- Notes: Expected typo-tolerant issue discovery with citations.
- Response excerpt:

```text
### Final Answer

### Executive Summary

The current grounded regulatory recommendation is **Additional Information Required**. The submission covers the product **Watch Review Demo** (levofloxacin), submitted by **Demo Applicant**. The structured review found **2** unresolved requirement-level concerns.

### Naming Policy Compliance

No INN infringement detected for 'Watch Review Demo'.

**AMR St
```

### S3 - query_expansion_stability
- Prompt: `review stablity snd shelf lif justifcation`
- Dossier: `SIM-STANDARD-20260417_213706`
- Passed: `True`
- Recommendation: `approval_granted`
- Route: `fallback`
- Citations: `6`
- Notes: Expected stability-oriented retrieval despite typos.
- Response excerpt:

```text
### Final Answer

### Executive Summary

The current grounded regulatory recommendation is **Approval Granted**. The submission covers the product **Standard Review Demo** (nitrofurantoin), submitted by **Demo Applicant**. The structured review found **1** unresolved requirement-level concern.

### Naming Policy Compliance

No INN infringement detected for 'Standard Review Demo'.

**AMR Stewardshi
```

### S4 - reranking_specificity
- Prompt: `focus on gmp cert expirry, not clinical`
- Dossier: `SIM-SCANNED-20260417_213706`
- Passed: `True`
- Recommendation: `additional_information_required`
- Route: `fallback`
- Citations: `2`
- Notes: Expected GMP-specific evidence to outrank unrelated clinical material.
- Response excerpt:

```text
### Final Answer

### Executive Summary

The current grounded regulatory recommendation is **Additional Information Required**. The submission covers the product **Scanned Review Demo** (levofloxacin), submitted by **Demo Applicant**. The structured review found **3** unresolved requirement-level concerns. The primary manufacturing site is identified as **Demo Manufacturer**, located in **Uganda**
```

### S5 - ambiguous_followup
- Prompt: `so can we move ahead with this one?`
- Dossier: `SIM-WATCH-20260417_213706`
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
- Dossier: `SIM-WATCH-20260417_213706`
- Passed: `True`
- Recommendation: `None`
- Route: `knowledge_wiki`
- Citations: `4`
- Notes: Expected routed guidance response using the unified assistant path.
- Response excerpt:

```text
I found guidance that is relevant to this review question:
- Active dossier context: **Watch Review Demo** (levofloxacin).
- WHO AWaRe and GLASS Policy Stack - AWaRe Source of Truth: WHO AWaRe and GLASS Policy Stack. AWaRe Source of Truth.AWaRe Source of Truth WHO AWaRe is the authoritative source for Access, Watch, and Reserve assignment. Production policy dec... [knowledge_wiki:who-aware-and-gla
```

### S7 - amr_stewardship_decision
- Prompt: `does this require restricted authoriztion and why?`
- Dossier: `SIM-WATCH-20260417_213706`
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
- Dossier: `SIM-STANDARD-20260417_213706`
- Passed: `True`
- Recommendation: `abstain`
- Route: `fallback`
- Citations: `0`
- Notes: Expected abstention or explicit silence when the dossier does not provide the requested fact.
- Response excerpt:

```text
Abstained because no evidence chunks were retrieved for the request.
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
- Dossier: `SIM-SCANNED-20260417_213706`
- Passed: `True`
- Recommendation: `additional_information_required`
- Route: `fallback`
- Citations: `2`
- Notes: Expected reasoning trace, final recommendation, and citations in the end-to-end pipeline.
- Response excerpt:

```text
### Final Answer

### Executive Summary

The current grounded regulatory recommendation is **Additional Information Required**. The submission covers the product **Scanned Review Demo** (levofloxacin), submitted by **Demo Applicant**. The structured review found **3** unresolved requirement-level concerns.

### Naming Policy Compliance

No INN infringement detected for 'Scanned Review Demo'.

**AM
```

## Final Review Report

- Dossier: `SIM-SCANNED-20260417_213706`
- HTML: `/v1/reports/report-15e7c9fbcf97/html`
- TXT: `/v1/reports/report-15e7c9fbcf97/text`
- JSON: `/v1/reports/report-15e7c9fbcf97/json`
