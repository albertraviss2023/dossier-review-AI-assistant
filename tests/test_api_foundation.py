from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import zipfile

from fastapi.testclient import TestClient

from dossier_review_ai_assistant.intake import parse_uploaded_document


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["dossiers_loaded"] >= 1200
    assert payload["sections_indexed"] > 0
    assert payload["model_policy"] == "local_multi_model"
    assert payload["retrieval_mode"] == "hybrid_bm25_densevector_rrf_rerank_v2"
    assert payload["external_source_mode"] in {"snapshot_only", "live_prefer"}
    assert payload["default_model_id"] == "gemma-e4b"
    assert payload["default_context_window_tokens"] == 4096
    assert len(payload["available_models"]) >= 3
    assert len(payload["chunking_profiles"]) >= 3
    assert any(profile["source_type"] == "dossier_section" for profile in payload["chunking_profiles"])
    assert payload["system_total_ram_gb"] >= payload["system_available_ram_gb"]


def test_login_page_and_auth_guard(api_module):
    raw_client = TestClient(api_module.app)
    page = raw_client.get("/login")
    assert page.status_code == 200
    assert "Sign in to continue" in page.text

    unauthenticated = raw_client.get("/v1/dossiers")
    assert unauthenticated.status_code == 401

    admin_redirect = raw_client.get("/admin", follow_redirects=False)
    assert admin_redirect.status_code in {303, 401}


def test_ui_pages_exist(client):
    review_page = client.get("/review")
    assert review_page.status_code == 200
    assert "Pre-Market Authorization" in review_page.text
    assert "Drug Review Assistant" in review_page.text
    assert "Pre-Market authorization starts with one clear review thread." in review_page.text
    assert "Advanced workspace" in review_page.text
    assert "Generate report" in review_page.text
    assert "Report library" in review_page.text
    assert "Open reasoning trace" in review_page.text
    assert "Trace log" in review_page.text
    assert "Open latest" in review_page.text
    assert "Review sessions" in review_page.text
    assert "Structured review type" in review_page.text
    assert "Sign out" in review_page.text
    assert "Admin panel" in review_page.text
    assert "Chart controls" in review_page.text
    assert "Continue analysis" in review_page.text
    assert "Swap axes" in review_page.text
    assert "Attach submission or annex" in review_page.text
    assert "Grounded review mode" in review_page.text
    assert "Enter to send" not in review_page.text
    assert "Submit new dossier" not in review_page.text
    assert "Upload New PDF..." in review_page.text
    assert "Try sample dossier" in review_page.text
    assert "Reference scenarios" not in review_page.text
    assert "Upload JSON Dossier" not in review_page.text
    assert "Review Conversation" not in review_page.text
    assert "MDR Risk Gauge" not in review_page.text
    assert "Evidence Density" not in review_page.text
    assert "Action Trace" not in review_page.text

    root_page = client.get("/")
    assert root_page.status_code == 200
    assert "Pre-Market authorization starts with one clear review thread." in root_page.text

    issues_page = client.get("/issues")
    assert issues_page.status_code == 200
    assert "/review?surface=issues" in issues_page.text

    wiki_page = client.get("/wiki")
    assert wiki_page.status_code == 200
    assert "/review?surface=wiki" in wiki_page.text

    amr_page = client.get("/amr")
    assert amr_page.status_code == 200
    assert "/review?surface=amr" in amr_page.text

    admin_page = client.get("/admin")
    assert admin_page.status_code == 200
    assert "Review Program Admin Panel" in admin_page.text
    assert "Program users" in admin_page.text


def test_brand_assets_exist(client):
    favicon = client.get("/favicon.svg")
    assert favicon.status_code == 200
    assert "svg" in favicon.text

    mark = client.get("/brand-mark.svg")
    assert mark.status_code == 200
    assert "svg" in mark.text


def test_model_catalog_endpoint(client):
    response = client.get("/v1/models")
    assert response.status_code == 200
    payload = response.json()
    assert payload["default_model_id"] == "gemma-e4b"
    assert {model["id"] for model in payload["available_models"]} >= {
        "gemma-e4b",
        "gemma-e2b",
        "gemma-26b",
    }


def test_list_dossiers_endpoint(client):
    response = client.get("/v1/dossiers?limit=5")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_items"] == 5
    assert len(payload["items"]) == 5
    assert payload["items"][0]["dossier_id"]
    assert payload["items"][0]["product_name"]


def test_get_dossier_endpoint(client, api_module):
    any_dossier_id = next(iter(api_module.state["dossier_by_id"].keys()))
    response = client.get(f"/v1/dossiers/{any_dossier_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["dossier_id"] == any_dossier_id
    assert "holistic_policy_decision" in payload["labels"]
    assert "aware_category" in payload["policy_signals"]


def test_retrieval_search_endpoint(client):
    response = client.post(
        "/v1/retrieval/search",
        json={"query": "Compare GMP certificate validity with pivotal trial outcome", "top_k": 5},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_hits"] > 0
    assert len(payload["citations"]) <= 5
    assert payload["citations"][0]["citation_id"]
    assert len(payload["sub_queries"]) >= 3


def test_knowledge_wiki_endpoints(client):
    list_response = client.get("/v1/knowledge-wiki")
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["total_pages"] >= 5
    assert any(page["page_id"] == "who-aware-and-glass" for page in list_payload["pages"])
    assert any(page["page_id"] == "external-source-provenance-and-audit" for page in list_payload["pages"])

    search_response = client.post(
        "/v1/knowledge-wiki/search",
        json={"query": "Reserve fast-track and Watch restriction", "top_k": 5},
    )
    assert search_response.status_code == 200
    search_payload = search_response.json()
    assert search_payload["total_hits"] > 0
    assert len(search_payload["sub_queries"]) >= 3
    assert all(citation["dossier_id"] == "knowledge_wiki" for citation in search_payload["citations"])

    source_response = client.post(
        "/v1/knowledge-wiki/search",
        json={"query": "What outside sources are consulted and how should provenance be reported in the review?", "top_k": 5},
    )
    assert source_response.status_code == 200
    source_payload = source_response.json()
    assert source_payload["total_hits"] > 0
    assert any("external-source-provenance-and-audit" in citation["citation_id"] for citation in source_payload["citations"])


def test_knowledge_graph_exposes_granular_review_dimensions(client):
    response = client.get("/v1/knowledge-graph")
    assert response.status_code == 200
    payload = response.json()
    summary = payload["summary_stats"]
    assert "product_groups" in summary
    assert "application_types" in summary
    assert "review_domains" in summary
    assert "by_product" in summary
    assert "by_inn" in summary
    assert any(node["type"] == "ProductGroup" for node in payload["nodes"])
    assert any(node["type"] == "ApplicationType" for node in payload["nodes"])
    assert any(node["type"] == "Recommendation" for node in payload["nodes"])
    assert any(node["type"] == "Manufacturer" for node in payload["nodes"])
    assert any(node["type"] == "SubmissionYear" for node in payload["nodes"])


def test_conversation_endpoints(client):
    create_response = client.post(
        "/v1/conversations",
        json={"title": "AMR review continuity", "model_id": "gemma-e2b", "context_window_tokens": 4096},
    )
    assert create_response.status_code == 200
    create_payload = create_response.json()
    assert create_payload["conversation"]["title"] == "AMR review continuity"
    assert create_payload["conversation"]["selected_model_id"] == "gemma-e2b"
    assert create_payload["conversation"]["context_monitor"]["context_window_tokens"] == 4096

    list_response = client.get("/v1/conversations")
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["total_items"] >= 1
    assert any(item["conversation_id"] == create_payload["conversation"]["conversation_id"] for item in list_payload["items"])

    delete_response = client.delete(f"/v1/conversations/{create_payload['conversation']['conversation_id']}")
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True

    missing_response = client.get(f"/v1/conversations/{create_payload['conversation']['conversation_id']}")
    assert missing_response.status_code == 404


def test_assistant_message_respects_selected_context_window(client):
    create_response = client.post(
        "/v1/conversations",
        json={"title": "Context window validation", "model_id": "gemma-e4b", "context_window_tokens": 16384},
    )
    assert create_response.status_code == 200
    conversation_id = create_response.json()["conversation"]["conversation_id"]

    response = client.post(
        "/v1/assistant/message",
        json={
            "workspace": "review",
            "question": "Hello friend",
            "conversation_id": conversation_id,
            "context_window_tokens": 16384,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["context_monitor"] is not None
    assert payload["context_monitor"]["context_window_tokens"] == 16384


def test_admin_user_registry_exposes_seeded_program_users(client):
    response = client.get("/v1/admin/users")
    assert response.status_code == 200
    payload = response.json()
    usernames = {item["username"] for item in payload["items"]}
    assert "alutakome" in usernames
    assert "ma_reviewer_1" in usernames
    assert "ma_reviewer_2" in usernames
    assert "ma_reviewer_3" in usernames
    assert "alutakome_ct" not in usernames
    assert all("marketing_authorization" in item["process_scopes"] for item in payload["items"])


def test_admin_can_create_and_disable_program_user(client):
    create_response = client.post(
        "/v1/admin/users",
        json={
            "username": "ma_temp_reviewer",
            "password": "dpar@2026#",
            "display_name": "Temporary MA Reviewer",
            "role": "reviewer",
            "process_scopes": ["marketing_authorization"],
        },
    )
    assert create_response.status_code == 200
    assert create_response.json()["username"] == "ma_temp_reviewer"

    disable_response = client.patch(
        "/v1/admin/users/ma_temp_reviewer",
        json={"active": False},
    )
    assert disable_response.status_code == 200
    assert disable_response.json()["active"] is False

    raw_client = TestClient(client.app)
    login_response = raw_client.post(
        "/v1/auth/login",
        json={"username": "ma_temp_reviewer", "password": "dpar@2026#"},
    )
    assert login_response.status_code == 403


def test_process_isolation_between_marketing_and_clinical_trial(api_module, client):
    ct_client = TestClient(api_module.app)
    login = ct_client.post("/v1/auth/login", json={"username": "alutakome_ct", "password": "dpar@2026#"})
    assert login.status_code == 200

    sample_response = ct_client.get("/v1/sample-intake-files")
    sample_item = sample_response.json()["items"][0]
    download_response = ct_client.get(sample_item["download_url"])
    assert download_response.status_code == 200

    intake_response = ct_client.post(
        "/v1/dossiers/intake",
        data={**_intake_form("INTAKE-CT-001"), "review_program": "clinical_trial"},
        files={"file": (sample_item["file_name"], download_response.content, sample_item["media_type"])},
    )
    assert intake_response.status_code == 200
    assert intake_response.json()["review_program"] == "clinical_trial"

    reviewer_block = client.get("/v1/dossiers/INTAKE-CT-001")
    assert reviewer_block.status_code == 403

    reviewer_list = client.get("/v1/dossiers").json()["items"]
    assert all(item["dossier_id"] != "INTAKE-CT-001" for item in reviewer_list)

    ct_visible = ct_client.get("/v1/dossiers/INTAKE-CT-001")
    assert ct_visible.status_code == 200
    assert ct_visible.json()["review_program"] == "clinical_trial"


def test_sample_dossiers_and_upload_endpoint(client):
    sample_response = client.get("/v1/sample-dossiers")
    assert sample_response.status_code == 200
    sample_payload = sample_response.json()
    assert sample_payload["total_items"] >= 6
    sample_item = sample_payload["items"][0]

    download_response = client.get(sample_item["download_url"])
    assert download_response.status_code == 200
    sample_dossier = download_response.json()
    sample_dossier["dossier_id"] = f"{sample_dossier['dossier_id']}-TEST"

    upload_response = client.post("/v1/dossiers/upload", json=sample_dossier)
    assert upload_response.status_code == 200
    upload_payload = upload_response.json()
    assert upload_payload["dossier_id"] == sample_dossier["dossier_id"]

    dossier_response = client.get(f"/v1/dossiers/{sample_dossier['dossier_id']}")
    assert dossier_response.status_code == 200
    assert dossier_response.json()["dossier_id"] == sample_dossier["dossier_id"]


def test_sample_incoming_files_endpoint_and_intake(client):
    sample_response = client.get("/v1/sample-intake-files")
    assert sample_response.status_code == 200
    sample_payload = sample_response.json()
    assert sample_payload["total_items"] >= 10
    assert all(item["media_type"] == "application/pdf" for item in sample_payload["items"])
    assert any(item["review_pathway"] for item in sample_payload["items"])
    assert any(item["document_condition"] for item in sample_payload["items"])
    assert any(item["expected_outcome"] for item in sample_payload["items"])
    descriptions = " ".join(item["description"].lower() for item in sample_payload["items"])
    assert "fast-track" in descriptions or "fast track" in descriptions
    assert "not acceptable" in descriptions or "deficient" in descriptions or "missing" in descriptions
    assert "deep review" in descriptions or "restricted" in descriptions
    assert "application" in descriptions
    assert "dossier" in descriptions or "submission" in descriptions

    sample_item = sample_payload["items"][0]
    download_response = client.get(sample_item["download_url"])
    assert download_response.status_code == 200

    response = client.post(
        "/v1/dossiers/intake",
        data=_intake_form("INTAKE-SAMPLE-PDF-001"),
        files={"file": (sample_item["file_name"], download_response.content, sample_item["media_type"])},
    )
    assert response.status_code == 200
    payload = response.json()
    stored = json.loads(Path(payload["stored_path"]).read_text(encoding="utf-8"))
    assert stored["provenance"]["extraction"]["extraction_method"].startswith("pdf_")
    assert "source_filename" in stored["provenance"]
    assert "visual_evidence" in stored["provenance"]["extraction"]


def _intake_form(dossier_id: str) -> dict[str, str]:
    return {
        "dossier_id": dossier_id,
        "country": "Uganda",
        "submission_date": "2026-04-11",
        "product_name": "Incoming Sample",
        "inn_name": "levofloxacin hemihydrate",
        "applicant": "Test Applicant",
        "manufacturer": "Test Manufacturer",
        "facility_country": "Uganda",
    }


def _minimal_docx_bytes(paragraphs: list[str]) -> bytes:
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        + "".join(f"<w:p><w:r><w:t>{paragraph}</w:t></w:r></w:p>" for paragraph in paragraphs)
        + "</w:body></w:document>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"></Relationships>'
    )
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


def _minimal_pdf_bytes(lines: list[str]) -> bytes:
    content_stream = "BT /F1 12 Tf 72 720 Td " + " ".join(f"({line}) Tj T*" for line in lines) + " ET"
    objects = [
        "1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj",
        "2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj",
        "3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >> endobj",
        f"4 0 obj << /Length {len(content_stream)} >> stream\n{content_stream}\nendstream endobj",
    ]
    pdf = "%PDF-1.4\n"
    offsets = [0]
    for obj in objects:
        offsets.append(len(pdf))
        pdf += obj + "\n"
    xref_start = len(pdf)
    pdf += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"
    for offset in offsets[1:]:
        pdf += f"{offset:010d} 00000 n \n"
    pdf += f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF"
    return pdf.encode("latin-1")


def test_raw_text_intake_endpoint(client):
    text = (
        "Manufacturer and GMP Evidence\n\n"
        "GMP certificate remains valid and no critical findings were reported.\n\n"
        "Clinical Overview and Benefit-Risk Summary\n\n"
        "Primary endpoint was met in the pivotal study.\n\n"
        "AMR Stewardship Narrative\n\n"
        "High similarity to ciprofloxacin with rising resistance supports restriction."
    ).encode("utf-8")
    response = client.post(
        "/v1/dossiers/intake",
        data=_intake_form("INTAKE-TXT-001"),
        files={"file": ("incoming.txt", text, "text/plain")},
    )
    assert response.status_code == 200
    dossier_response = client.get("/v1/dossiers/INTAKE-TXT-001")
    assert dossier_response.status_code == 200
    assert dossier_response.json()["product"]["inn_name"] == "levofloxacin hemihydrate"


def test_docx_intake_endpoint(client):
    docx_bytes = _minimal_docx_bytes(
        [
            "Manufacturer and GMP Evidence",
            "GMP certificate remains valid and CAPA closure evidence is attached.",
            "Clinical Overview and Benefit-Risk Summary",
            "Primary endpoint was met in the pivotal program.",
        ]
    )
    response = client.post(
        "/v1/dossiers/intake",
        data=_intake_form("INTAKE-DOCX-001"),
        files={"file": ("incoming.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert response.status_code == 200
    dossier_response = client.get("/v1/dossiers/INTAKE-DOCX-001")
    assert dossier_response.status_code == 200
    assert dossier_response.json()["dossier_id"] == "INTAKE-DOCX-001"


def test_pdf_intake_endpoint(client):
    pdf_bytes = _minimal_pdf_bytes(
        [
            "Manufacturer and GMP Evidence",
            "GMP certificate remains valid.",
            "AMR Stewardship Narrative",
            "High similarity to ciprofloxacin with rising resistance supports restriction.",
        ]
    )
    response = client.post(
        "/v1/dossiers/intake",
        data=_intake_form("INTAKE-PDF-001"),
        files={"file": ("incoming.pdf", pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200
    dossier_response = client.get("/v1/dossiers/INTAKE-PDF-001")
    assert dossier_response.status_code == 200
    assert dossier_response.json()["dossier_id"] == "INTAKE-PDF-001"


def test_scanned_pdf_uses_ocr_for_difficult_intake():
    root = Path(r"d:\projects\ai dossier assistant")
    path = root / "sample_dossiers" / "incoming_files" / "incoming_scanned_quality_failure.pdf"
    parsed = parse_uploaded_document(path.name, path.read_bytes())
    normalized_text = parsed.text.lower().replace(" ", "")

    assert parsed.ocr_used is True
    assert parsed.extraction_method in {"pdf_ocr", "pdf_text_plus_ocr"}
    assert "certificateexpired" in normalized_text
    assert "primaryendpointwasnotmet" in normalized_text
    assert len(parsed.visual_evidence) >= 1
    assert any("summary" in item for item in parsed.visual_evidence)


def test_scanned_pdf_can_complete_review_and_report_workflow(client):
    root = Path(r"d:\projects\ai dossier assistant")
    path = root / "sample_dossiers" / "incoming_files" / "incoming_scanned_quality_failure.pdf"

    intake_response = client.post(
        "/v1/dossiers/intake",
        data=_intake_form("INTAKE-SCANNED-WORKFLOW-001"),
        files={"file": (path.name, path.read_bytes(), "application/pdf")},
    )
    assert intake_response.status_code == 200

    step1_response = client.post(
        "/v1/review",
        json={
            "dossier_id": "INTAKE-SCANNED-WORKFLOW-001",
            "question": "Perform data quality and vision extraction check for this dossier.",
            "review_type": "generic",
        },
    )
    assert step1_response.status_code == 200

    review_response = client.post(
        "/v1/review",
        json={
            "dossier_id": "INTAKE-SCANNED-WORKFLOW-001",
            "question": "Review this dossier, complete the structured workflow, and provide the final recommendation with citations.",
            "review_type": "generic",
        },
    )
    assert review_response.status_code == 200
    review_payload = review_response.json()
    assert "findings_summary_markdown" in review_payload
    assert review_payload["workflow_summary"] is not None

    report_response = client.post(
        "/v1/reports/generate",
        json={
            "dossier_id": "INTAKE-SCANNED-WORKFLOW-001",
            "review_payload": review_payload,
            "conversation_id": review_payload["conversation_id"],
            "review_type": "generic",
            "report_title": "Scanned Workflow Report",
        },
    )
    assert report_response.status_code == 200
    assert report_response.json()["word_download_url"]


def test_review_report_generation_and_download(client, api_module):
    any_dossier_id = next(iter(api_module.state["dossier_by_id"].keys()))
    review_response = client.post(
        "/v1/review",
        json={
            "dossier_id": any_dossier_id,
            "question": "Review this dossier and recommend the next regulatory action with citations.",
            "top_k": 5,
        },
    )
    assert review_response.status_code == 200
    review_payload = review_response.json()

    report_response = client.post(
        "/v1/reports/generate",
        json={
            "dossier_id": any_dossier_id,
            "review_payload": review_payload,
            "conversation_id": review_payload["conversation_id"],
            "report_title": "Reviewer Decision Report",
            "recipient_email": "review.board@example.org",
        },
    )
    assert report_response.status_code == 200
    report_payload = report_response.json()
    assert report_payload["report_title"] == "Reviewer Decision Report"
    assert report_payload["html_download_url"]
    assert report_payload["text_download_url"]
    assert report_payload["word_download_url"]
    assert report_payload["json_download_url"]
    assert report_payload["query_letter_download_url"]
    assert report_payload["decision_log_download_url"]
    assert "Reviewer Decision Report" in report_payload["email_subject"]

    html_download = client.get(report_payload["html_download_url"])
    text_download = client.get(report_payload["text_download_url"])
    word_download = client.get(report_payload["word_download_url"])
    json_download = client.get(report_payload["json_download_url"])
    query_letter_download = client.get(report_payload["query_letter_download_url"])
    decision_log_download = client.get(report_payload["decision_log_download_url"])

    assert html_download.status_code == 200
    assert text_download.status_code == 200
    assert word_download.status_code == 200
    assert json_download.status_code == 200
    assert query_letter_download.status_code == 200
    assert decision_log_download.status_code == 200
    assert "Overall Judgment" in html_download.text
    assert "AMR Stewardship Review" in html_download.text
    assert "WHO INN Similarity Review" in text_download.text
    assert "Findings Register" in text_download.text
    assert word_download.content.startswith(b"PK")
    json_payload = json_download.json()
    assert json_payload["recipient_email"] == "review.board@example.org"
    assert "workflow_report" in json_payload["report_payload"]
    assert "overall_judgment" in json_payload["report_payload"]["workflow_report"]
    assert "query_letter" in json_payload["report_payload"]
    assert "decision_log" in json_payload["report_payload"]

    repository_response = client.get("/v1/reports")
    assert repository_response.status_code == 200
    repository_payload = repository_response.json()
    assert repository_payload["total_items"] >= 1
    assert any(item["report_id"] == report_payload["report_id"] for item in repository_payload["items"])
    matching = next(item for item in repository_payload["items"] if item["report_id"] == report_payload["report_id"])
    assert matching["application_type"] in {"new_application", "renewal"}
    assert matching["product_group"]
    assert matching["word_download_url"]

    antimicrobial_response = client.get("/v1/reports?antimicrobial_only=true")
    assert antimicrobial_response.status_code == 200


def test_benchmark_panel_endpoint_returns_metrics(client):
    response = client.get("/v1/benchmark/panel")
    assert response.status_code == 200
    payload = response.json()
    assert "metrics" in payload
    assert isinstance(payload["metrics"], list)


def test_review_report_generation_is_blocked_until_sop_steps_are_complete(client, api_module):
    any_dossier_id = next(iter(api_module.state["dossier_by_id"].keys()))
    review_response = client.post(
        "/v1/review",
        json={
            "dossier_id": any_dossier_id,
            "question": "What product is being submitted and who is the applicant?",
            "top_k": 5,
        },
    )
    assert review_response.status_code == 200
    review_payload = review_response.json()

    report_response = client.post(
        "/v1/reports/generate",
        json={
            "dossier_id": any_dossier_id,
            "review_payload": review_payload,
            "conversation_id": review_payload["conversation_id"],
            "report_title": "Too Early Report",
        },
    )
    assert report_response.status_code == 409
    detail = report_response.json()["detail"]
    assert "cannot be generated yet" in detail["message"].lower()
    assert "who_inn_similarity_review" in detail["missing_steps"]
    assert any("WHO INN similarity review" == label for label in detail["missing_step_labels"])


def test_superuser_can_reject_report_and_reopen_dossier(client, api_module):
    any_dossier_id = next(iter(api_module.state["dossier_by_id"].keys()))
    review_response = client.post(
        "/v1/review",
        json={
            "dossier_id": any_dossier_id,
            "question": "Review this dossier, complete all workflow steps, and provide the final recommendation with citations.",
            "top_k": 5,
            "review_type": "generic",
        },
    )
    assert review_response.status_code == 200
    review_payload = review_response.json()

    report_response = client.post(
        "/v1/reports/generate",
        json={
            "dossier_id": any_dossier_id,
            "review_payload": review_payload,
            "conversation_id": review_payload["conversation_id"],
            "review_type": "generic",
            "report_title": "Rejectable Report",
        },
    )
    assert report_response.status_code == 200
    report_id = report_response.json()["report_id"]

    reject_response = client.post(
        f"/v1/reports/{report_id}/reject",
        json={"reason": "Supervisor requested clarification before approval."},
    )
    assert reject_response.status_code == 200
    assert reject_response.json()["status"] == "reopened"

    dossier_response = client.get(f"/v1/dossiers/{any_dossier_id}")
    assert dossier_response.status_code == 200
    assert dossier_response.json()["status"] == "reopened"


def test_review_response_exposes_routed_intent_and_packet_contract(client, api_module):
    any_dossier_id = next(iter(api_module.state["dossier_by_id"].keys()))
    response = client.post(
        "/v1/review",
        json={
            "dossier_id": any_dossier_id,
            "question": "What guidance and dossier evidence should I compare before confirming the recommendation?",
            "top_k": 5,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] in {"wiki_guidance", "mixed_compare_synthesize", "dossier_review", "policy_guidance"}


def test_first_review_turn_always_starts_with_data_quality_summary(client, api_module):
    any_dossier_id = next(iter(api_module.state["dossier_by_id"].keys()))
    response = client.post(
        "/v1/review",
        json={
            "dossier_id": any_dossier_id,
            "question": "What is the product name and applicant?",
            "top_k": 5,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert "### Data Quality Check (Mandatory Step 1)" in payload["rationale"]


def test_generic_and_innovation_review_branches_return_workflow_summary(client):
    dossier_listing = client.get("/v1/dossiers")
    assert dossier_listing.status_code == 200
    dossier_ids = [item["dossier_id"] for item in dossier_listing.json()["items"]]

    generic_payload = None
    for dossier_id in dossier_ids:
        generic_response = client.post(
            "/v1/review",
            json={
                "dossier_id": dossier_id,
                "question": "Complete the structured review workflow and give the final recommendation with citations.",
                "review_type": "generic",
            },
        )
        assert generic_response.status_code == 200
        generic_candidate = generic_response.json()
        if generic_candidate.get("workflow_summary") is not None:
            generic_payload = generic_candidate
            break

    assert generic_payload is not None
    assert generic_payload["review_type"] == "generic"
    assert generic_payload["findings_summary_markdown"]
    assert generic_payload["response_contract"]
    assert generic_payload["model_packet_version"] == "reason_and_route_v2"

    innovation_payload = None
    for dossier_id in dossier_ids:
        innovation_response = client.post(
            "/v1/review",
            json={
                "dossier_id": dossier_id,
                "question": "Complete the structured review workflow and give the final recommendation with citations.",
                "review_type": "innovator",
            },
        )
        assert innovation_response.status_code == 200
        innovation_candidate = innovation_response.json()
        if innovation_candidate.get("workflow_summary") is not None:
            innovation_payload = innovation_candidate
            break

    assert innovation_payload is not None
    assert innovation_payload["review_type"] == "innovator"
    assert "### External vs Submitted Evidence (Patient/Safety)" not in innovation_payload["rationale"]


def test_assistant_message_supports_chat_wiki_and_review_routing(client, api_module):
    any_dossier_id = next(iter(api_module.state["dossier_by_id"].keys()))

    chat_response = client.post(
        "/v1/assistant/message",
        json={"workspace": "review", "question": "Hi friend"},
    )
    assert chat_response.status_code == 200
    chat_payload = chat_response.json()
    assert chat_payload["intent"] == "chat_only"
    assert chat_payload["route"] == "chat_only"
    assert "hi friend" in chat_payload["rationale"].lower()

    wiki_response = client.post(
        "/v1/assistant/message",
        json={"workspace": "wiki", "question": "What guidance should I consult before confirming a recommendation?"},
    )
    assert wiki_response.status_code == 200
    wiki_payload = wiki_response.json()
    assert wiki_payload["intent"] == "wiki_guidance"
    assert wiki_payload["route"] == "knowledge_wiki"
    assert len(wiki_payload["citations"]) >= 1

    sop_response = client.post(
        "/v1/assistant/message",
        json={"workspace": "review", "question": "Show me the SOPs for dossier review."},
    )
    assert sop_response.status_code == 200
    sop_payload = sop_response.json()
    assert sop_payload["intent"] == "wiki_guidance"
    assert "practical guide" in sop_payload["rationale"].lower() or "structured dossier review sop" in sop_payload["rationale"].lower()
    assert any("structured-dossier-review-sop" in citation["citation_id"] for citation in sop_payload["citations"])

    tutorial_response = client.post(
        "/v1/assistant/message",
        json={"workspace": "review", "question": "Show me how to generate a reviewer report and explain it as a short tutorial."},
    )
    assert tutorial_response.status_code == 200
    tutorial_payload = tutorial_response.json()
    assert tutorial_payload["intent"] == "wiki_guidance"
    assert "practical guide" in tutorial_payload["rationale"].lower()
    assert any("reviewer-how-to-tutorials" in citation["citation_id"] for citation in tutorial_payload["citations"])

    review_response = client.post(
        "/v1/assistant/message",
        json={
            "workspace": "review",
            "dossier_id": any_dossier_id,
            "question": "Review this dossier and summarize the key issues with citations.",
            "top_k": 5,
        },
    )
    assert review_response.status_code == 200
    review_payload = review_response.json()
    assert review_payload["intent"] in {"dossier_review", "issue_discovery"}
    assert review_payload["route"] in {"standard", "fallback"}
    assert review_payload["recommendation"] in {"approval_granted", "approval_denied", "additional_information_required", "abstain"}

    visualization_response = client.post(
        "/v1/assistant/message",
        json={
            "workspace": "review",
            "question": "Plot the approval distribution as a chart.",
        },
    )
    assert visualization_response.status_code == 200
    visualization_payload = visualization_response.json()
    assert visualization_payload["intent"] == "visualization"
    assert visualization_payload["visualization_data"] is not None

    graph_response = client.post(
        "/v1/assistant/message",
        json={
            "workspace": "review",
            "question": "Show me the dossier relationship graph for the reviewed submissions.",
        },
    )
    assert graph_response.status_code == 200
    graph_payload = graph_response.json()
    assert graph_payload["intent"] == "visualization"
    assert graph_payload["visualization_data"] is not None
    assert graph_payload["visualization_data"]["type"] == "network"

    amr_distribution_response = client.post(
        "/v1/assistant/message",
        json={
            "workspace": "review",
            "question": "Plot the approval distribution for antimicrobial dossiers as a chart.",
        },
    )
    assert amr_distribution_response.status_code == 200
    amr_distribution_payload = amr_distribution_response.json()
    assert amr_distribution_payload["intent"] == "visualization"
    assert amr_distribution_payload["visualization_data"] is not None

    dossier_chart_response = client.post(
        "/v1/assistant/message",
        json={
            "workspace": "review",
            "dossier_id": any_dossier_id,
            "question": "Plot the approval trend for this dossier as a chart.",
        },
    )
    assert dossier_chart_response.status_code == 200
    dossier_chart_payload = dossier_chart_response.json()
    viz = dossier_chart_payload["visualization_data"]
    if viz is not None and viz.get("type") != "network":
        dossier = api_module.state["dossier_by_id"][any_dossier_id]
        expected_tag = f'{dossier.get("organization", {}).get("manufacturer", "")} | {dossier.get("product", {}).get("product_name", "")}'.strip(" |")
        assert expected_tag in viz.get("title", "")


def test_assistant_message_handles_typo_greeting_and_guidance_requests(client, api_module):
    any_dossier_id = next(iter(api_module.state["dossier_by_id"].keys()))

    greeting_response = client.post(
        "/v1/assistant/message",
        json={"workspace": "review", "question": "hi fried"},
    )
    assert greeting_response.status_code == 200
    greeting_payload = greeting_response.json()
    assert greeting_payload["intent"] == "chat_only"
    assert "hello" in greeting_payload["rationale"].lower() or "hi friend" in greeting_payload["rationale"].lower()

    guidance_response = client.post(
        "/v1/assistant/message",
        json={
            "workspace": "review",
            "dossier_id": any_dossier_id,
            "question": "what reviwer guidnce and who aware poicy applies here?",
            "top_k": 5,
        },
    )
    assert guidance_response.status_code == 200
    guidance_payload = guidance_response.json()
    assert guidance_payload["intent"] in {"wiki_guidance", "policy_guidance", "mixed_compare_synthesize"}
    assert guidance_payload["route"] == "knowledge_wiki"
    assert "guidance" in guidance_payload["rationale"].lower()
    assert len(guidance_payload["citations"]) >= 1


def test_review_response_includes_chain_of_thought_trace(client, api_module):
    any_dossier_id = next(iter(api_module.state["dossier_by_id"].keys()))
    response = client.post(
        "/v1/review",
        json={
            "dossier_id": any_dossier_id,
            "question": "Review this dossier, identify missing or contradictory evidence, explain the key issues, and give a recommendation with citations.",
            "top_k": 5,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["chain_of_thought"] is not None
    assert payload["findings_summary_markdown"]
    assert "| Severity | Violated rule | Evidence reference | Recommendation |" in payload["findings_summary_markdown"]
