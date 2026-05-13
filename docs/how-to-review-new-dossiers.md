# How To Review New Dossiers And Generate Reports

This guide is for non-technical reviewers.

It explains how to:
- open the system
- find new sample dossiers
- intake a submitted PDF dossier
- review the dossier
- generate a downloadable reviewer report
- repeat the process for several dossiers in one demo session

## What This Tool Is For

The Pre-Market Authorization Drug Review Assistant helps a reviewer assess a newly submitted dossier, retrieve relevant evidence, summarize findings across review criteria, and generate a reviewer-facing report.

In the reviewer workflow, new dossiers are treated as submitted PDF files.
The reviewer should not need to upload JSON files.

## Before You Start

You need two things running:

1. The support services with Docker
2. The review application itself

### Start The Support Services

Open PowerShell in the project folder and run:

```powershell
docker compose -f docker-compose.local.yml up -d
```

You can check that the support services are running with:

```powershell
docker compose -f docker-compose.local.yml ps
```

### Start The Review Application

In PowerShell, run:

```powershell
& "C:\Users\alber\AppData\Local\Programs\Python\Python311\python.exe" -m uvicorn dossier_review_ai_assistant.api:app --app-dir src --host 127.0.0.1 --port 8000
```

When the app is running, open:

```text
http://127.0.0.1:8000/review
```

## Where To Find Sample New Dossiers

The project already contains sample incoming PDF dossiers that simulate new manufacturer submissions.

They are stored here:

[`sample_dossiers/incoming_files`](/d:/projects/ai%20dossier%20assistant/sample_dossiers/incoming_files)

Current sample incoming PDFs:

1. [`incoming_standard_review_submission.pdf`](/d:/projects/ai%20dossier%20assistant/sample_dossiers/incoming_files/incoming_standard_review_submission.pdf)
2. [`incoming_watch_submission.pdf`](/d:/projects/ai%20dossier%20assistant/sample_dossiers/incoming_files/incoming_watch_submission.pdf)
3. [`incoming_scanned_quality_failure.pdf`](/d:/projects/ai%20dossier%20assistant/sample_dossiers/incoming_files/incoming_scanned_quality_failure.pdf)

You can also access these from the Review page under `Incoming PDF Samples`.

## Recommended Demo Scenario

For a clear multi-dossier demo, review these three in order:

1. `incoming_standard_review_submission.pdf`
This shows a more routine case.

2. `incoming_watch_submission.pdf`
This shows a stewardship-sensitive Watch case.

3. `incoming_scanned_quality_failure.pdf`
This shows a difficult scanned PDF and a likely quality failure scenario.

This gives you a simple demonstration of:
- a standard review path
- a stewardship-heavy review path
- a difficult PDF plus quality-risk path

## Step-By-Step Workflow For One New Dossier

### Step 1. Open The Review Page

Go to:

```text
http://127.0.0.1:8000/review
```

This is the main decision workspace.

### Step 2. Choose A New Submitted PDF

On the right side of the page, open `Incoming PDF Samples`.

Choose one of the sample PDFs and click `Intake Sample`.

If you want to use your own local PDF instead:

1. In the main intake section, choose the submitted PDF file
2. Enter the basic metadata:
   - product name
   - INN name
   - applicant
   - manufacturer
   - country
   - facility country
   - submission date
3. Click `Intake File`

What happens next:
- the system extracts the PDF contents
- if the PDF is image-heavy or scanned, OCR is used automatically
- the system creates a reviewable dossier ID

### Step 3. Confirm The Dossier

After intake, the `Dossier ID` field is populated.

Click `Preview`.

This lets you confirm:
- the dossier was created
- the product and applicant are correct
- the system recognized the dossier as a reviewable case

### Step 4. Ask For The Review Decision

In the `Decision Request` box, keep the default wording or use something like:

```text
Review this dossier, summarize findings across all review criteria, identify any missing or contradictory evidence, and recommend the next regulatory action with citations.
```

Then click `Run Review`.

The system will return:
- the recommendation
- the review route
- the rationale
- findings across criteria
- citations
- stewardship outputs where applicable

### Step 5. Generate The Reviewer Report

After the review result appears, click:

```text
Generate Report
```

The system will create a reviewer-facing report from the current decision and findings.

The report includes:
- executive summary
- findings across criteria
- section-level diagnostics
- stewardship and verification information
- supporting citations

### Step 6. Download Or Share The Report

After the report is generated, use:

- `Download HTML`
- `Download TXT`
- `Email Draft`

Use these depending on how you want to present the output.

The HTML report is the best option for a polished, readable review package.

## How To Review Several New Dossiers In One Demo

Repeat the same cycle for each sample PDF.

Use this sequence:

1. Intake `incoming_standard_review_submission.pdf`
2. Preview it
3. Run the review
4. Generate and download the report
5. Repeat with `incoming_watch_submission.pdf`
6. Repeat with `incoming_scanned_quality_failure.pdf`

This gives a complete demonstration across multiple new incoming dossiers.

## Suggested Demo Script

If you are presenting the system to others, this is a simple script to follow:

1. “We start from a newly submitted PDF dossier.”
2. “We intake the PDF and the system creates a reviewable case.”
3. “We preview the dossier to confirm the product and submission details.”
4. “We run the review and the tool summarizes findings across all key criteria.”
5. “The system gives a recommendation supported by citations.”
6. “We then generate a reviewer report that can be downloaded or shared.”
7. “We repeat the same workflow for additional new dossiers.”

## What Each Sample Demonstrates

### `incoming_standard_review_submission.pdf`

Use this to show:
- a cleaner intake path
- a more routine review flow
- a standard review scenario

### `incoming_watch_submission.pdf`

Use this to show:
- AMR stewardship relevance
- Watch-category concerns
- a dossier where stewardship meaningfully influences the decision

### `incoming_scanned_quality_failure.pdf`

Use this to show:
- scanned or difficult PDF handling
- OCR fallback
- a quality-risk or reject-and-return style scenario

## If The Reviewer Wants To Continue A Case Later

The system also supports chat continuity, but that is intentionally hidden behind the `Advanced` drawer.

For most demos, you do not need to use it.

Use it only if you want to show:
- continuing a previous review conversation
- linked review discussions
- follow-up questions on the same dossier

## If The UI Does Not Open

Check:

1. Docker services are up
2. The application is running on port `8000`

Quick checks:

```powershell
docker compose -f docker-compose.local.yml ps
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/health
```

If `/health` does not respond, restart the app command.

## What To Do When Retrieval Fails

If the review output says "no chunks found" or returns no dossier evidence, treat this as a pipeline issue rather than a normal review finding.

1. Confirm the intake completed successfully.
   - there should be a valid `Dossier ID`
   - the dossier preview should show the product name, applicant, country, and section list
2. Confirm the PDF extraction path.
   - if the document is scanned, OCR should have been applied automatically
   - check whether the dossier preview or admin page shows `OCR` or `scanned` status
3. Confirm the dossier contains required review sections.
   - each dossier should include clearly labeled evidence sections such as GMP, clinical data, AMR/Watch, and chemistry
   - missing sections should be reported as "evidence absent" rather than allowing the model to default to "no chunks"
4. If the document is malformed, retry with a cleaner PDF or a native text-based file.

## Correct vs Incorrect Submission Format

A correct dossier submission should include:
- `product` metadata with `product_name`, `inn_name`, `atc_code`, `dosage_form`, `strength`
- `organization` metadata with `applicant`, `manufacturer`, and `facility_country`
- `policy_signals` that match the dossier evidence and are not left empty
- a `sections` array containing structured evidence with titles, module labels, section text, and section-level metadata
- `labels` that reflect the expected review decision and whether the submission is compliant
- `provenance` that explicitly marks synthetic cases and defect modes for test coverage

Incorrect submissions commonly have:
- missing or empty dossier sections
- broken OCR/extracted text in scanned PDFs
- inconsistent or contradictory policy signals
- top-level metadata that does not match the dossier contents
- no evidence citations even when the prompt requests them

## How To Validate Chunking, Embedding, And MCP End-to-End

Use these commands in the project root to confirm the retrieval pipeline is healthy:

```powershell
python -m pytest tests/test_chunking.py tests/test_retrieval.py
python scripts/test_mcp_end_to_end.py
```

If you need a deeper smoke test, run:

```powershell
python scripts/run_mcp_realistic_simulations.py
```

A healthy end-to-end system should:
- create chunks for each dossier section with provenance metadata
- allow embeddings to be generated and queried via the vector search tool
- return search hits with section titles, dossier IDs, and snippet citations
- route retrieval through the MCP tool layer using `search_vector_database` and `rerank_search_results`
- synthesize reviewer answers that reference dossier evidence or explicitly note evidence absence

## Summary

For a non-technical reviewer, the real workflow is:

1. Open the Review page
2. Intake a submitted PDF dossier
3. Preview the created case
4. Run the review
5. Generate the reviewer report
6. Download or share the report
7. Repeat for the next newly submitted dossier

That is the recommended end-to-end demo path for this system.
