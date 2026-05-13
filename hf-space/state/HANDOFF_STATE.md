# UI, Workflow, And Review Intelligence State

Date: 2026-04-20

Completed in this session:
- Confirmed and improved the unified review UI so the left rail shows dossier review session history instead of a debug-style trace panel.
- Kept only the context usage counter visible in the header and removed the leftover dashboard-style gauges.
- Fixed context-window handling in the review UI so the selected value is persisted, sent with assistant requests, and reflected back from the conversation monitor instead of appearing stuck at 4K.
- Standardized visible role labels in the conversation thread to `Reviewer` and `Assistant`.
- Made response controls steadier and more predictable in the assistant message footer.
- Preserved the expandable reasoning trace so reviewers can inspect the structured reasoning summary without exposing raw hidden chain-of-thought.
- Cleaned AMR stewardship wording so reviewer-facing answers summarize source-backed facts naturally instead of dumping raw snapshot artifacts into the response body.
- Added an outside-source governance wiki page covering consulted-source reporting, source precedence, and workflow analytics expectations.
- Added dedicated SOP and reviewer tutorial knowledge pages so reviewers can ask natural questions like "Show me the SOPs for dossier review" or "Show me how to generate a report."
- Improved wiki guidance filtering so provenance and external-source questions surface the relevant guidance page.
- Expanded natural-language visualization support to cover:
  - approval/recommendation distribution
  - approval trends
  - AWaRe distribution
  - naming and other recorded violations
  - submission distribution by country
  - dossier relationship graph / knowledge graph views
- Added support for rendering dossier relationship graphs in the review UI plot overlay.
- Added a report repository endpoint and UI browser so previously generated reports can be browsed by product group, application type, antimicrobial relevance, and final verdict.
- Added per-conversation clear/delete support so saved review chats can be removed directly from the left session history.
- Expanded the knowledge graph to include product groups, application types, review domains, recommendation nodes, and product/INN-specific rollups for more granular querying and plotting.
- Upgraded the plot overlay into an editable chart workspace with:
  - chart-type switching
  - palette switching
  - axis swapping for bar charts
  - clearer axis labels and legends
  - smoother close behavior
  - follow-up analysis chips so plotting does not end the workflow
- Saved a fresh demo run showing context-window honor, outside-source guidance retrieval, and dossier graph output.

Files changed in this phase:
- `ui/review.html`
- `src/dossier_review_ai_assistant/api.py`
- `src/dossier_review_ai_assistant/inference.py`
- `src/dossier_review_ai_assistant/knowledge_graph.py`
- `state/knowledge_wiki.json`
- `tests/test_api_foundation.py`
- `tests/test_review_quality.py`

Validation completed:
- `python -m pytest tests/test_api_foundation.py -q` passed
- `python -m pytest tests/test_review_quality.py -q` passed
- `python -m pytest -q` passed (`1 skipped` Playwright-style browser test remains opt-in)

Demo artifacts:
- `state/reports/ui_workflow_demo_20260420_092645.md`
- `state/reports/ui_workflow_demo_20260420_092645.json`
- `state/reports/chart_workflow_demo_20260420_101802.md`
- `state/reports/chart_workflow_demo_20260420_101802.json`
- `state/reports/report_library_demo_20260420_104038.md`
- `state/reports/report_library_demo_20260420_104038.json`
- `state/reports/graph_and_history_demo_20260420_110751.md`
- `state/reports/graph_and_history_demo_20260420_110751.json`

Current product state:
- Unified assistant workflow is intact.
- Structured regulatory workflow reporting is intact.
- Outside-source governance guidance is now represented in the wiki.
- Natural graph/plot queries are broader and include dossier relationship graph output.
- Context-window selection is explicitly tested and respected through the assistant endpoint.
- SOP enforcement is now active for final report generation:
  - the system tracks workflow-step completion per dossier and per conversation
  - report generation is blocked until mandatory SOP review steps are completed
  - the UI now surfaces a clear missing-steps message when a reviewer tries to generate the report too early
- Production-foundation requirements were updated in:
  - `docs/requirements-spec.md`
  - `docs/acceptance-criteria.yaml`
- Authentication and RBAC are now in place:
  - branded login page at `ui/login.html`
  - session-based auth middleware
  - reviewer isolation by default
  - default superuser `alutakome`
- Dossier lifecycle state is now tracked:
  - `open`
  - `in_review`
  - `done`
  - `reopened`
- Reports can be rejected by a superuser, which reopens the dossier while preserving prior report history.
- Review type plumbing is now present through the request/response stack with `generic` and `innovation` values persisted in lifecycle and report records.
- A dedicated structured review helper now powers both live review responses and report generation:
  - `src/dossier_review_ai_assistant/review_workflow.py`
- Generic review now supports innovator-baseline comparison when `reference_materials` are present in the dossier payload.
- Innovation review now checks completeness, clarity, required patient-information content, and regulatory adequacy without requiring wording equivalence to an innovator baseline.
- Findings summary markdown tables are now generated across review areas and are available in:
  - live review responses
  - report JSON payloads
  - report text and Word exports
- Demo dossier realism was improved:
  - `sample_dossiers/standard_review_access_sample.json` now includes a true administrative section, product-information section, stability section, and innovator baseline references
  - `sample_dossiers/innovation_clarity_sample.json` was added as an innovation-review showcase dossier
- Process-scoped review governance is now in place:
  - supported review programs are `marketing_authorization` and `clinical_trial`
  - seeded users now include:
    - marketing authorization superuser `alutakome`
    - clinical trial superuser `alutakome_ct`
    - three marketing authorization reviewers
    - three clinical trial reviewers
  - dossier, report, and knowledge-graph access now respect review-program scope
- A superuser-only admin panel is now available at `ui/admin.html` and `/admin`:
  - list users in the current admin's allowed review program
  - create reviewer or superuser accounts
  - grant or revoke access by enabling/disabling accounts
- The review UI was hardened for day-to-day use:
  - visible microphone button for browser speech input where supported
  - stronger click-to-focus behavior in the composer
  - improved scroll behavior for chat history and main thread through `min-h-0` / bounded scroll containers
- OCR/image-heavy review workflow is now explicitly validated through a scanned PDF intake -> review -> report path
- `_infer_review_program` was tightened so ordinary pre-market dossiers with clinical study sections are not misclassified as clinical-trial reviews

Validation completed for SOP enforcement:
- `python -m pytest tests/test_api_foundation.py -q` passed
- `python -m pytest tests/test_reporting.py -q` passed
- `python -m pytest -q` passed (`2 skipped` opt-in browser checks)

Validation completed for auth/RBAC/lifecycle slice:
- `python -m pytest tests/test_api_foundation.py -q` passed
- `python -m pytest tests/test_reporting.py -q` passed
- `python -m pytest -q` passed (`2 skipped` opt-in browser checks)

Validation completed for structured generic/innovation review slice:
- `python -m pytest tests/test_structured_review_workflow.py -q` passed
- `python -m pytest tests/test_reporting.py -q` passed
- `python -m pytest tests/test_api_foundation.py -q` passed
- `python -m pytest -q` passed (`2 skipped` opt-in browser checks)

Validated live review examples:
- Generic dossier demo (`UPLOAD-STANDARD-001-R4`) produced:
  - recommendation `approval_granted`
  - final verdict `acceptable`
  - review-type-specific status `adequate`
- Innovation dossier demo (`UPLOAD-INNOVATION-001-R3`) produced:
  - recommendation `approval_granted`
  - final verdict `acceptable`
  - review-type-specific status `adequate`

Validation completed for process/admin/OCR hardening slice:
- `python -m pytest tests/test_api_foundation.py -q` passed
- `python -m pytest tests/test_reporting.py tests/test_intake_realism.py -q` passed
- `python -m pytest -q` completed with a fully passing summary plus `2 skipped` opt-in browser checks, but this Windows host left the pytest process open long enough for the tool timeout after printing success

Known honest gap:
- Review-program governance and access isolation are now implemented for `clinical_trial` vs `marketing_authorization`.
- A distinct clinical-trial protocol review engine has not been built yet; CT currently has separate users, access controls, and dossier segregation, but not a fully separate scientific workflow comparable to the marketing-authorization structured review engine.

Reasonable next focus if work continues:
1. Build a dedicated clinical-trial protocol workflow engine so CT review logic is as rich as the current marketing-authorization workflow.
2. Expose the structured findings tables more directly in the UI as dedicated reviewer cards instead of only inside markdown response content.
3. Add first-class intake fields and storage for `submission_type`, `application_type`, and explicit innovator-reference attachments instead of relying on dossier payload structure alone.
