# Hackathon Case Studies

## 1. Pass Case (Human, Non-AMR)
- Scenario: complete pre-market dossier with aligned admin, quality, clinical, and labeling evidence.
- Expected result: `acceptable` or `acceptable_with_conditions`.
- Demo prompt:
  - `Run full SOP review with data quality first and provide a pass-focused verdict with confidence and trace.`

## 2. AMR Query Case (Human Antimicrobial)
- Scenario: Watch/Reserve antimicrobial with missing stewardship justification or warning alignment gaps.
- Expected result: `query_applicant` or `requires_revision`.
- Demo prompt:
  - `Run full SOP review with AMR stewardship focus, identify gaps, and provide query-applicant verdict with trace.`

## 3. Veterinary Withdrawal-Risk Query Case
- Scenario: veterinary antimicrobial with missing withdrawal/residue details for food-producing species.
- Expected result: `query_applicant`.
- Demo prompt:
  - `Run full SOP review with veterinary withdrawal/residue safety focus and provide verdict with trace.`

## Demo Notes
- Use `Resilience Mode` in UI to force local fallback and show low-connectivity continuity.
- Follow each case with:
  - `show sop status`
- In the final recap, show:
  - External vs submitted reconciliation tables
  - Safety & Trust verdict trace table
  - Judge pack exports (`HTML` and `PDF`)
