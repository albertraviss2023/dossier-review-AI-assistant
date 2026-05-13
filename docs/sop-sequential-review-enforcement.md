# SOP Sequential Review Enforcement

## Purpose
This document defines the mandatory step-by-step regulatory review sequence enforced by the application.  
Reviewers must proceed in order. The assistant blocks out-of-order requests that skip required prior steps.

## Enforcement Rules
1. Reviews follow a strict ordered sequence.
2. A step is considered complete only after a corresponding review interaction is performed and recorded.
3. Requests that jump ahead are rejected with a workflow-gate response, including:
- requested step
- next required step
- completed steps
- missing steps
4. Final verdict/report generation is allowed only after all required steps are completed.

## Mandatory Step Order
1. Submission intake and familiarization
2. Administrative completeness review
3. Structural dossier mapping
4. Applicable rules and requirements identification
5. WHO INN similarity review
6. Section-by-section technical review
7. AMR stewardship review using AWaRe rules (required only when AMR is applicable)
8. Identification and recording of findings
9. Severity classification
10. Cross-section consistency review
11. Review completeness confirmation
12. Overall judgment (final verdict)

## Stage Intent (What Reviewer Should Ask)
1. Intake/Familiarization
- Confirm submission type, product identity, applicant, and dossier context.
2. Administrative Completeness
- Verify signed forms, fee/payment evidence, mandatory admin attachments.
3. Structural Mapping
- Verify required sections/modules are present and readable.
4. Applicable Rules
- Confirm governing checklist/rules for the specific review type and product class.
5. INN Similarity
- Evaluate product naming risk against WHO INN references.
6. Technical Review
- Assess quality, GMP, clinical, stability, and evidence adequacy by section.
7. AMR Stewardship (conditional)
- Evaluate AWaRe category, reserve/watch cautions, and stewardship controls.
8. Findings Register
- Record concrete deficiencies/issues with evidence references.
9. Severity Classification
- Classify findings into critical/major/minor/advisory.
10. Cross-section Consistency
- Check internal consistency across claims, labels, sections, and evidence.
11. Completeness Confirmation
- Confirm all mandatory workflow steps and unresolved blockers.
12. Overall Judgment
- Provide final regulatory verdict only after steps 1-11 are complete.

## Reviewer UX Expectations
1. If a reviewer asks for AMR before completing earlier steps, the system must block and instruct the next required step.
2. If a reviewer asks for final verdict early, the system must block and require completion of prior stages.
3. Findings and verdict outputs must remain evidence-grounded and citation-backed.

## Citation Display Convention
1. Assistant response references are numeric in reading order, e.g. `[1] [2] [3]`.
2. Citation numbers are assigned top-to-bottom by first appearance.
3. Hovering each number shows the referenced source chunk preview (section title + snippet + dossier reference).

