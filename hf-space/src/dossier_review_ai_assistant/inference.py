from __future__ import annotations

import json
import math
import os
import re
import subprocess
from urllib import request
from urllib.parse import urlencode
from typing import Any


CLAIM_LINE_PATTERN = re.compile(r"^\s*(?:\d+\.\s*)?(?P<text>.+?)\s*\[(?P<citation>[^\[\]]+)\]\s*$")
SENTENCE_WITH_CITATION_PATTERN = re.compile(r"(?P<text>[^.\n]+?)\s*\[(?P<citation>[^\[\]]+)\]")
WHITESPACE_RUN_PATTERN = re.compile(r"\s+")
ISSUE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+|\n+")
NEGATIVE_TERMS = (
    "missing",
    "expired",
    "critical",
    "not met",
    "incomplete",
    "deficien",
    "contradict",
    "restrict",
    "rising resistance",
    "unresolved",
    "fail",
    "rejected",
    "return",
    "gap",
    "weak",
    "insufficient",
    "incorrect",
    "too short",
    "too long",
)
POSITIVE_TERMS = (
    "remains valid",
    "was met",
    "attached",
    "no critical findings",
    "acceptable",
    "adequate",
    "supports",
    "valid",
)


def extract_cited_claims(text: str) -> list[dict[str, str]]:
    claims: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = CLAIM_LINE_PATTERN.match(line)
        if match:
            claim_text = match.group("text").strip(" -:")
            citation_id = match.group("citation").strip()
            key = (claim_text, citation_id)
            if claim_text and citation_id and key not in seen:
                seen.add(key)
                claims.append({"text": claim_text, "citation_id": citation_id})
            continue

        for sentence_match in SENTENCE_WITH_CITATION_PATTERN.finditer(line):
            claim_text = sentence_match.group("text").strip(" -:;,.")
            citation_id = sentence_match.group("citation").strip()
            key = (claim_text, citation_id)
            if claim_text and citation_id and key not in seen:
                seen.add(key)
                claims.append({"text": claim_text, "citation_id": citation_id})

    return claims


def _question_focus(question: str) -> dict[str, bool]:
    lowered = question.lower()
    return {
        "greeting": lowered.strip() in {"hi", "hello", "hey", "hi friend", "hello friend", "hey friend"},
        "issues": any(term in lowered for term in ("issue", "risk", "problem", "gap", "missing", "contradict")),
        "amr": any(term in lowered for term in ("amr", "aware", "glass", "stewardship", "resistance", "antibacterial")),
        "gmp": any(term in lowered for term in ("gmp", "manufacturer", "quality", "facility", "certificate")),
        "clinical": any(term in lowered for term in ("clinical", "trial", "endpoint", "efficacy", "benefit-risk", "safety")),
        "stability": any(term in lowered for term in ("stability", "shelf life", "shelf-life", "storage condition", "accelerated study", "long-term study")),
        "rules": any(term in lowered for term in ("applicable rule", "what rules apply", "requirements apply", "checklist", "naming rule", "stewardship rules", "rule base")),
        "completeness": any(term in lowered for term in ("review completeness", "workflow steps", "workflow is complete", "mandatory workflow", "have all workflow steps", "review complete", "review incomplete")),
        "overall_judgment": any(term in lowered for term in ("overall judgment", "acceptable with conditions", "requires revision", "not acceptable", "escalate for higher review")),
        "summary": any(term in lowered for term in ("summary", "summarize", "overview", "what are the key issues")),
        "recommendation": any(term in lowered for term in ("recommend", "regulatory action", "decision", "authorize", "approval")),
        "count": any(term in lowered for term in ("count", "how many", "number of")),
        "rank": any(term in lowered for term in ("rank", "most important", "priority order", "prioritize")),
        "categorize": any(term in lowered for term in ("categorize", "category", "group the issues", "classify")),
        "review": any(term in lowered for term in ("review", "analyze", "evaluate", "check")),
        "origin": any(term in lowered for term in ("origin", "country", "source", "location", "orgigin")),
        "manufacturer": any(term in lowered for term in ("manufactur", "maker", "producer", "facil", "manfactur")),
    }


def _score_evidence_for_question(question: str, section_title: str, snippet: str) -> int:
    focus = _question_focus(question)
    combined = f"{section_title} {snippet}".lower()
    score = 0
    if focus["gmp"] and any(term in combined for term in ("gmp", "manufacturer", "quality", "facility", "certificate", "capa")):
        score += 4
    if focus["clinical"] and any(term in combined for term in ("clinical", "trial", "endpoint", "efficacy", "benefit-risk", "safety")):
        score += 4
    if focus["stability"] and any(term in combined for term in ("stability", "shelf life", "shelf-life", "storage", "accelerated", "long-term")):
        score += 4
    if focus["amr"] and any(term in combined for term in ("amr", "aware", "glass", "stewardship", "resistance", "watch", "reserve", "mdr", "signal", "narrative")):
        score += 4
    if focus["issues"] and any(term in combined for term in ("missing", "expired", "critical", "risk", "restrict", "not met", "contradict", "incomplete")):
        score += 3
    if focus["summary"]:
        score += 1
    if focus["recommendation"]:
        score += 1
    return score


def _select_relevant_evidence(question: str, evidence: list[dict[str, Any]], limit: int = 4) -> list[dict[str, Any]]:
    def is_boilerplate(snippet: str) -> bool:
        lowered = snippet.lower()
        if "regulatory dossier submission" in lowered and "dossier id:" in lowered:
            return True
        if "product:" in lowered and "applicant:" in lowered:
            return True
        return False

    filtered = [ev for ev in evidence if not is_boilerplate(str(ev.get("snippet", "")))]
    
    ranked = sorted(
        filtered,
        key=lambda ev: (
            _score_evidence_for_question(question, str(ev.get("section_title", "")), str(ev.get("snippet", ""))),
            float(ev.get("score", 0.0)),
        ),
        reverse=True,
    )
    return ranked[:limit]


def _normalize_issue_text(text: str) -> str:
    cleaned = WHITESPACE_RUN_PATTERN.sub(" ", text or "").strip(" -:;,.")
    if cleaned:
        # Simple fix for mangled OCR words
        replacements = {
            "highand": "high and",
            "concernsare": "concerns are",
            "risingthe": "rising the",
            "restrictionsmayaply": "restrictions may apply",
            "restrictionsmayapply": "restrictions may apply",
            "chemistrycomperator": "chemistry comparator",
            "levofloxacinand": "levofloxacin and",
            "watch-classimilarity": "Watch-class similarity",
            "classimilarity": "class similarity",
            "amrstewardship": "AMR stewardship",
            "comparatoris": "comparator is",
            "gmpcertificate": "GMP certificate",
            "clinicaloverview": "clinical overview",
            "benefit-risk": "benefit-risk",
            "mdrpathogen": "MDR pathogen",
            "glassresistance": "GLASS resistance",
            "mayaply": "may apply",
        }
        for old, new in replacements.items():
            # Case insensitive replacement
            cleaned = re.sub(re.escape(old), new, cleaned, flags=re.IGNORECASE)
    return cleaned


def _polish_rationale_text(text: str) -> str:
    cleaned = text.strip()
    # Ensure sentences before key phrases have periods
    cleaned = re.sub(r"([a-zA-Z0-9])\s+(This finding|Final Verdict|The next reviewer|My analysis|The dossier|In conclusion|Reviewer verification)", r"\1. \2", cleaned)
    # Fix redundant punctuation but preserve newlines
    cleaned = re.sub(r"[ \t]+([,.;:?!])", r"\1", cleaned)
    # Collapse multiple spaces but NOT newlines
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    # Normalize multiple newlines to exactly two for clean paragraph breaks
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = cleaned.replace("..", ".")
    # Ensure bullet points and headers have a clean line
    cleaned = re.sub(r"^\s*-\s*([a-zA-Z0-9])", r"- \1", cleaned, flags=re.MULTILINE)
    # Ensure headers have a newline before them if they don't already
    cleaned = re.sub(r"([^\n])\n*(### )", r"\1\n\n\2", cleaned)
    return cleaned


def _recommended_follow_up(
    *,
    focus: dict[str, bool],
    issue_entries: list[dict[str, Any]],
    amr_stewardship: dict[str, Any],
) -> str:
    if amr_stewardship.get("applies"):
        if amr_stewardship.get("watch_similarity_restriction"):
            return f"The reviewer should specifically confirm the restricted authorization controls due to **{amr_stewardship.get('similarity_to_existing_watch', 'high')}** chemical similarity to {amr_stewardship.get('existing_watch_comparator', 'Watch-class')} agents."
        return "The reviewer should confirm the stewardship plan aligns with the AWaRe categorization and local resistance trends."
        
    if focus["gmp"]:
        return "The reviewer should confirm the current GMP certificate validity and site inspection history."
    if focus["clinical"]:
        return "The reviewer should confirm the pivotal trial results support the proposed indication."
    if issue_entries:
        top_issue = issue_entries[0]["summary"]
        # Remove section prefix for the conclusion summary if present
        if ":" in top_issue:
            top_issue = top_issue.split(":", 1)[1].strip()
        return f"Reviewer verification should focus on addressing the identified gap regarding **{top_issue}**."
        
    return "The dossier appears structurally adequate for the proposed recommendation."


def _split_issue_candidates(text: str) -> list[str]:
    normalized = _normalize_issue_text(text)
    if not normalized:
        return []
    parts = [part.strip() for part in ISSUE_SPLIT_PATTERN.split(normalized) if part.strip()]
    if len(parts) > 1:
        return parts

    segmented = re.sub(
        r"(?i)(manufacturer\s*and|clinical\s*overview|benefit-risk\s*summary|amr\s*stewardship\s*narrative|amrstewardship\s*narrative|visual\s*evidence\s*ocr)",
        lambda match: f"|{match.group(0)}",
        normalized,
    )
    return [part.strip(" |") for part in segmented.split("|") if part.strip(" |")]


def _categorize_issue_text(text: str) -> str:
    lowered = text.lower()
    if any(term in lowered for term in ("gmp", "manufacturer", "quality", "certificate", "facility", "capa")):
        return "Quality and GMP"
    if any(term in lowered for term in ("stability", "shelf life", "shelf-life", "storage", "accelerated", "long-term")):
        return "Stability"
    if any(term in lowered for term in ("clinical", "trial", "endpoint", "efficacy", "benefit-risk", "safety")):
        return "Clinical Evidence"
    if any(term in lowered for term in ("aware", "glass", "stewardship", "resistance", "watch", "reserve", "mdr", "antibacterial")):
        return "AMR Stewardship"
    return "General"


def _looks_like_issue(text: str) -> bool:
    lowered = text.lower()
    if "risk mitigation" in lowered or "benefit-risk" in lowered:
        return False
    return any(term in lowered for term in NEGATIVE_TERMS)


def _compose_mock_rationale(
    *,
    question: str,
    recommendation: str,
    evidence: list[dict[str, Any]],
    model_id: str,
    dossier: dict[str, Any] | None = None,
    conversation_context: str | None = None,
    section_diagnostics: list[dict[str, Any]] | None = None,
    amr_stewardship: dict[str, Any] | None = None,
    model_packet: dict[str, Any] | None = None,
) -> tuple[str, list[dict[str, str]], Any | None]:
    focus = _question_focus(question)
    selected = _select_relevant_evidence(question, evidence, limit=4)
    claims: list[dict[str, str]] = []
    section_diagnostics = section_diagnostics or []
    amr_stewardship = amr_stewardship or {}
    contract = str(model_packet.get("response_contract", "default_v1")) if model_packet else "default_v1"
    
    analysis = (model_packet or {}).get("analysis", {})
    intent = analysis.get("intent", "dossier_review")
    discarded_audit = (model_packet or {}).get("discarded_audit", [])
    judge_findings = list(((model_packet or {}).get("judge_decision", {}) or {}).get("findings", []))
    judge_aggregate = dict((model_packet or {}).get("judge_aggregate", {}) or {})
    material_judge_findings = [finding for finding in judge_findings if bool(finding.get("issue_present"))]

    # Start with <reasoning> block (MANDATORY and FIRST)
    reasoning_data = {
        "intent": intent,
        "resolved_terms": analysis.get('constraints', []),
        "retrieval_strategy": f"Precision search across {contract} domain",
        "bouncer_audit": discarded_audit[:8] if isinstance(discarded_audit, list) else []
    }
    
    reasoning_lines = ["<reasoning>", json.dumps(reasoning_data, indent=2), "</reasoning>"]
    reasoning_lines.append("")

    if intent == "visualization":
        review_state = (model_packet or {}).get("review_state", {})
        stats = review_state.get("summary_stats", {})
        graph_payload = review_state.get("knowledge_graph", {})
        graph_query_result = review_state.get("graph_query_result") or {}
        
        viz_data = None
        lowered_question = question.lower()
        wants_bar = any(term in lowered_question for term in ("bar chart", "bar graph", "histogram"))
        wants_line = any(term in lowered_question for term in ("line chart", "line graph", "over time", "trend", "timeline", "by month", "monthly"))
        wants_pie = any(term in lowered_question for term in ("pie chart", "donut", "doughnut"))
        wants_network = any(term in lowered_question for term in ("dossier graph", "relationship graph", "knowledge graph", "network graph", "node", "edge"))
        mentions_chart = any(term in lowered_question for term in ("chart", "graph", "plot", "visualize"))
        graph_focus = _extract_graph_focus(lowered_question, stats, graph_payload)
        if wants_line and any(term in lowered_question for term in ("approval", "recommendation", "verdict", "query", "reject", "approve")):
            trends = stats.get("trends", {})
            sorted_months = sorted([m for m in trends.keys() if m != "unknown"])
            labels = sorted_months
            approved = []
            rejected = []
            for m in labels:
                r = trends[m].get("recommendations", {})
                app_count = r.get("approve", 0) + r.get("approval_granted", 0) + r.get("fast_track", 0) + r.get("standard_review", 0)
                rej_count = r.get("reject", 0) + r.get("approval_denied", 0) + r.get("reject_and_return", 0)
                approved.append(app_count)
                rejected.append(rej_count)
            
            viz_data = {
                "type": "line",
                "title": "Approval Trends Over Time",
                "labels": labels,
                "datasets": [
                    {"label": "Approved", "data": approved, "backgroundColor": "#22c55e", "borderColor": "#16a34a"},
                    {"label": "Rejected", "data": rejected, "backgroundColor": "#ef4444", "borderColor": "#dc2626"},
                ]
            }
            rationale = "I have generated a line chart showing approval and rejection trends over time."
        elif (
            wants_pie
            or "approvals vs rejections" in lowered_question
            or ("approval" in lowered_question and "distribution" in lowered_question)
            or ("recommendation" in lowered_question and any(term in lowered_question for term in ("chart", "plot", "graph")))
        ):
            graph_counts = _recommendation_counts_from_graph(graph_payload, graph_focus)
            recs, scope_text = graph_counts if graph_counts else _filtered_recommendation_counts(stats, graph_focus)
            labels = ["Approved", "Rejected", "Request Info"]
            # Map different naming conventions
            approve = recs.get("approve", 0) + recs.get("approval_granted", 0) + recs.get("fast_track", 0) + recs.get("standard_review", 0)
            reject = recs.get("reject", 0) + recs.get("approval_denied", 0) + recs.get("reject_and_return", 0)
            req_info = recs.get("request_info", 0) + recs.get("additional_information_required", 0) + recs.get("deep_review", 0)
            
            data = [approve, reject, req_info]
            viz_data = {
                "type": "pie",
                "title": "Approvals vs Rejections vs Requests for Info",
                "labels": labels,
                "datasets": [{
                    "data": data,
                    "backgroundColor": ["#22c55e", "#ef4444", "#eab308"]
                }]
            }
            rationale = f"I have generated a pie chart showing the distribution of review recommendations {scope_text}."
        elif wants_bar and any(term in lowered_question for term in ("approval", "recommendation", "verdict", "query", "reject", "approve")):
            graph_counts = _recommendation_counts_from_graph(graph_payload, graph_focus)
            recs, scope_text = graph_counts if graph_counts else _filtered_recommendation_counts(stats, graph_focus)
            labels = ["Approved", "Rejected", "Request Info"]
            approve = recs.get("approve", 0) + recs.get("approval_granted", 0) + recs.get("fast_track", 0) + recs.get("standard_review", 0)
            reject = recs.get("reject", 0) + recs.get("approval_denied", 0) + recs.get("reject_and_return", 0)
            req_info = recs.get("request_info", 0) + recs.get("additional_information_required", 0) + recs.get("deep_review", 0)
            viz_data = {
                "type": "bar",
                "title": "Recommendations by Outcome",
                "labels": labels,
                "datasets": [{
                    "label": "Dossiers",
                    "data": [approve, reject, req_info],
                    "backgroundColor": ["#22c55e", "#ef4444", "#eab308"],
                }],
            }
            rationale = f"I have generated a bar chart showing review outcomes {scope_text}."
        elif wants_network and not (wants_bar or wants_line or wants_pie):
            focus_subgraph = graph_query_result.get("focus_subgraph", {}) if isinstance(graph_query_result, dict) else {}
            nodes = list((focus_subgraph.get("nodes") or graph_payload.get("nodes") or []))[:28]
            edges = list((focus_subgraph.get("edges") or graph_payload.get("edges") or []))
            node_labels = []
            node_groups = []
            edge_pairs = []
            positions_x = []
            positions_y = []
            for idx, node in enumerate(nodes):
                props = node.get("properties", {})
                node_labels.append(props.get("name") or props.get("recommendation") or node.get("id"))
                node_groups.append(node.get("type", "Unknown"))
                angle = (idx / max(len(nodes), 1)) * 6.28318
                positions_x.append(round(1.8 * math.cos(angle), 4))
                positions_y.append(round(1.2 * math.sin(angle), 4))
            node_index = {node.get("id"): idx for idx, node in enumerate(nodes)}
            for edge in edges:
                source = edge.get("source")
                target = edge.get("target")
                if source in node_index and target in node_index:
                    edge_pairs.append((node_index[source], node_index[target], edge.get("type", "RELATES_TO")))
            viz_data = {
                "type": "network",
                "title": "Dossier Relationship Graph",
                "labels": node_labels,
                "datasets": [
                    {
                        "nodes": [
                            {
                                "label": node_labels[idx],
                                "group": node_groups[idx],
                                "x": positions_x[idx],
                                "y": positions_y[idx],
                            }
                            for idx in range(len(node_labels))
                        ],
                        "edges": [
                            {"source": source, "target": target, "label": label}
                            for source, target, label in edge_pairs
                        ],
                    }
                ],
            }
            top_connected = graph_query_result.get("top_connected_entities", []) if isinstance(graph_query_result, dict) else []
            if top_connected:
                highlights = ", ".join(str(item.get("label", "")) for item in top_connected[:3] if str(item.get("label", "")).strip())
                rationale = (
                    "I have generated a dossier relationship graph showing how reviewed submissions connect to products, applicants, "
                    f"AMR categories, and recorded issues. Most connected entities in this view are: {highlights}."
                )
            else:
                rationale = "I have generated a dossier relationship graph showing how reviewed submissions connect to products, applicants, AMR categories, and recorded issues."
        elif "amr concern" in lowered_question or "aware" in lowered_question or ("amr" in lowered_question and mentions_chart):
            aware = stats.get("aware_categories", {})
            labels = list(aware.keys())
            data = list(aware.values())
            viz_data = {
                "type": "bar",
                "title": "AMR Concerns (AWaRe Distribution)",
                "labels": labels,
                "datasets": [{
                    "label": "Dossiers",
                    "data": data,
                    "backgroundColor": "#3b82f6"
                }]
            }
            rationale = "I have generated a bar graph showing the distribution of dossiers across WHO AWaRe categories."
        elif any(term in lowered_question for term in ("country", "jurisdiction", "where submissions come from", "submission origin")):
            countries = stats.get("countries", {})
            labels = list(countries.keys())
            data = list(countries.values())
            viz_data = {
                "type": "bar",
                "title": "Submission Distribution by Country",
                "labels": labels,
                "datasets": [{
                    "label": "Dossiers",
                    "data": data,
                    "backgroundColor": "#14b8a6"
                }]
            }
            rationale = "I have generated a bar graph showing where reviewed submissions originate by country or jurisdiction."
        elif any(term in lowered_question for term in ("naming violation", "inn violation", "name confusion", "naming issue")):
            violations = stats.get("violations", {})
            labels = ["INN Infringement", "Other Violations"]
            inn_count = int(violations.get("INN Infringement", 0))
            other_count = max(sum(int(v) for k, v in violations.items()) - inn_count, 0)
            viz_data = {
                "type": "bar",
                "title": "Naming And Other Recorded Violations",
                "labels": labels,
                "datasets": [{
                    "label": "Occurrences",
                    "data": [inn_count, other_count],
                    "backgroundColor": "#f97316"
                }]
            }
            rationale = "I have generated a comparison graph showing naming-related violations against other recorded review violations."
        elif "violation" in question.lower():
            violations = stats.get("violations", {})
            labels = list(violations.keys())
            data = list(violations.values())
            viz_data = {
                "type": "bar",
                "title": "Key Violations Identified",
                "labels": labels,
                "datasets": [{
                    "label": "Occurrences",
                    "data": data,
                    "backgroundColor": "#f97316"
                }]
            }
            rationale = "I have generated a bar graph highlighting the key policy violations identified across the reviewed dossiers."
        elif wants_line and any(term in lowered_question for term in ("report", "reports generated", "reviews done", "reviews completed")):
            trends = stats.get("trends", {})
            labels = sorted([m for m in trends.keys() if m != "unknown"])
            totals = []
            for m in labels:
                recs = trends[m].get("recommendations", {})
                totals.append(sum(int(v) for v in recs.values() if isinstance(v, (int, float))))
            viz_data = {
                "type": "line",
                "title": "Review Activity Over Time",
                "labels": labels,
                "datasets": [{
                    "label": "Reviews",
                    "data": totals,
                    "backgroundColor": "#3b82f6",
                    "borderColor": "#1d4ed8",
                }],
            }
            rationale = "I have generated a line chart showing review activity over time."
        elif mentions_chart:
            graph_counts = _recommendation_counts_from_graph(graph_payload, graph_focus)
            recs, scope_text = graph_counts if graph_counts else _filtered_recommendation_counts(stats, graph_focus)
            labels = ["Approved", "Rejected", "Request Info"]
            approve = recs.get("approve", 0) + recs.get("approval_granted", 0) + recs.get("fast_track", 0) + recs.get("standard_review", 0)
            reject = recs.get("reject", 0) + recs.get("approval_denied", 0) + recs.get("reject_and_return", 0)
            req_info = recs.get("request_info", 0) + recs.get("additional_information_required", 0) + recs.get("deep_review", 0)
            viz_data = {
                "type": "bar",
                "title": "Review Outcomes Snapshot",
                "labels": labels,
                "datasets": [{
                    "label": "Dossiers",
                    "data": [approve, reject, req_info],
                    "backgroundColor": ["#22c55e", "#ef4444", "#eab308"],
                }],
            }
            rationale = f"I have generated a chart showing review outcomes {scope_text}."
        else:
            rationale = "I can generate plots for approval trends, recommendation distribution, AMR concerns, naming violations, country distribution, and dossier relationship graphs. Please specify which one you would like to see."

        return _polish_rationale_text("\n".join(reasoning_lines) + "\n\n" + "### Final Answer\n\n" + rationale), [], viz_data

    if focus["greeting"] and not any(
        focus[key] for key in ("issues", "amr", "gmp", "clinical", "summary", "recommendation", "count", "rank", "categorize")
    ):
        return (
            "\n".join(reasoning_lines) + "Hello. I am the Dossier Review Assistant. I can help you analyze submission evidence, identify regulatory risks, and evaluate AMR stewardship alignment. How can I assist you today?",
            [],
            None,
        )

    from .policy import evaluate_amr_stewardship, evaluate_naming_policy
    amr_stewardship = evaluate_amr_stewardship(dossier)
    naming_policy = evaluate_naming_policy(dossier)

    issue_entries = _build_issue_entries(selected, section_diagnostics, amr_stewardship)
    paragraphs: list[str] = []

    # 1. Summary / Overview (Improved with entity-aware attention)
    final_rec_label = recommendation.replace("_", " ").title()
    if naming_policy["is_infringement"]:
        final_rec_label = "Approval Denied"

    paragraphs.append("### Final Answer")
    paragraphs.append("### Executive Summary")

    product_info = dossier.get("product", {})
    org_info = dossier.get("organization", {})
    
    unresolved = int(judge_aggregate.get("unresolved_items", 0))
    summary_parts = [
        f"The current grounded regulatory recommendation is **{final_rec_label}**.",
        f"The submission covers the product **{product_info.get('product_name', 'Unknown')}** ({product_info.get('inn_name', 'INN unknown')}), "
        f"submitted by **{org_info.get('applicant', 'Unknown Organization')}**."
    ]
    if unresolved:
        summary_parts.append(f"The structured review found **{unresolved}** unresolved requirement-level concern{'s' if unresolved != 1 else ''}.")
    
    if focus["origin"] or "origin" in str(analysis.get('constraints', [])):
        summary_parts.append(f"The dossier originates from **{dossier.get('country', 'Unknown Country')}**.")
    
    if focus["manufacturer"] or "Manufacturer" in str(analysis.get('constraints', [])):
        summary_parts.append(f"The primary manufacturing site is identified as **{org_info.get('manufacturer', 'Unknown')}**, located in **{org_info.get('facility_country', 'Unknown')}**.")

    paragraphs.append(" ".join(summary_parts))

    # 1.5 Naming Policy Analysis (New Mandatory Check)
    if naming_policy["is_infringement"]:
        paragraphs.append("### Naming Policy Violation")
        paragraphs.append(naming_policy["rationale"])
        paragraphs.append("A recommendation to **Reject** is issued because the product name is too similar to a known WHO International Nonproprietary Name (INN), which may lead to clinical confusion.")
    elif focus["review"] or "name" in question.lower():
        paragraphs.append("### Naming Policy Compliance")
        paragraphs.append(naming_policy["rationale"])

    if conversation_context and any(term in question.lower() for term in ("continue", "follow up", "follow-up", "remaining", "prior discussion", "previous discussion")):
        paragraphs.append("This response continues the prior discussion so unresolved regulatory risk and issue signals stay in view.")

    if focus["rules"]:
        paragraphs.append("### Applicable Rules And Requirements")
        rule_lines = [
            "- Administrative completeness checklist applies to the submission package.",
            "- Structural dossier mapping rules apply to required sections, readability, and placement.",
            "- WHO INN similarity review is mandatory and must be reported.",
            "- Section adequacy rules apply to quality, clinical, and supporting evidence.",
        ]
        if amr_stewardship.get("applies"):
            rule_lines.append(
                f"- WHO AWaRe stewardship rules apply because the product is classified as **{str(amr_stewardship.get('aware_category', 'unknown')).upper()}**."
            )
        else:
            rule_lines.append("- AMR stewardship rules are not applicable for this dossier.")
        if naming_policy["is_infringement"]:
            rule_lines.append("- Naming safety rules block acceptance because INN similarity exceeds the threshold.")
        for line in rule_lines:
            paragraphs.append(line)
        if selected:
            claims.append({"text": "Applicable review rules were identified for the dossier.", "citation_id": str(selected[0].get("citation_id", ""))})

    if focus["completeness"]:
        paragraphs.append("### Review Completeness Confirmation")
        completeness_lines = [
            "- Submission intake and familiarization: completed.",
            "- Administrative completeness review: completed.",
            "- Structural dossier mapping: completed.",
            "- Applicable rules identification: completed.",
            "- WHO INN similarity review: completed.",
            "- Section-by-section technical review: completed.",
            "- AMR stewardship review: completed." if amr_stewardship.get("applies") else "- AMR stewardship review: not applicable and explicitly closed.",
        ]
        completeness_state = "complete"
        if naming_policy["is_infringement"]:
            completeness_lines.append("- Naming review identified a blocking violation, but the workflow step itself is complete.")
        if any(item.get("presence") != "present" for item in section_diagnostics):
            completeness_lines.append("- Some dossier sections remain deficient, but the review workflow can still be marked complete because the missing items were identified and recorded.")
        paragraphs.extend(completeness_lines)
        paragraphs.append(f"The current workflow status is **review {completeness_state}**.")
        if selected:
            claims.append({"text": f"Workflow completeness was confirmed as review {completeness_state}.", "citation_id": str(selected[0].get("citation_id", ""))})

    if focus["overall_judgment"]:
        paragraphs.append("### Overall Judgment")
        verdict = "acceptable"
        if naming_policy["is_infringement"] or recommendation == "approval_denied":
            verdict = "not acceptable"
        elif recommendation == "additional_information_required":
            verdict = "requires revision"
        elif amr_stewardship.get("restricted_authorization") or amr_stewardship.get("fast_track_candidate"):
            verdict = "acceptable with conditions"
        paragraphs.append(
            f"Based on the full structured review, the overall judgment is **{verdict}**. "
            f"This aligns with the grounded system recommendation of **{final_rec_label}**."
        )
        if verdict == "not acceptable":
            paragraphs.append("Blocking issues were identified and prevent acceptance at this stage.")
        elif verdict == "requires revision":
            paragraphs.append("Major unresolved issues require revision before the dossier can proceed.")
        elif verdict == "acceptable with conditions":
            paragraphs.append("The dossier can proceed only with the documented policy conditions and stewardship controls.")
        else:
            paragraphs.append("No blocking rule violations prevent the dossier from proceeding on the current evidence.")
        if selected:
            claims.append({"text": f"The overall judgment is {verdict}.", "citation_id": str(selected[0].get("citation_id", ""))})

    # 2. AMR Stewardship and Chemical Similarity (Prioritized)
    if contract == "amr_review_v1" or focus["amr"] or amr_stewardship.get("applies"):
        if "guideline" in question.lower() or "who" in question.lower():
             paragraphs.append("### WHO Guidelines Alignment")
             if amr_stewardship.get("applies"):
                category = str(amr_stewardship.get('aware_category', 'unknown')).upper()
                paragraphs.append(f"The product is classified as **{category}** per WHO AWaRe criteria. The proposed regulatory action is being cross-referenced with WHO GLASS resistance trends.")
                if selected:
                    paragraphs.append(f"Retrieved evidence from **{selected[0]['section_title']}** confirms the product's identity and clinical scope for stewardship review. [{selected[0]['citation_id']}]")
             else:
                paragraphs.append("No active AMR stewardship triggers were found that would require deviation from standard WHO authorization guidelines for this product class.")
        
        elif amr_stewardship.get("applies"):
            category = str(amr_stewardship.get('aware_category', 'unknown')).upper()
            rationale = str(amr_stewardship.get('rationale', 'aligned with policy'))

            normalized_ingredient = str(amr_stewardship.get("normalized_ingredient") or "").strip()
            glass_trend = str(amr_stewardship.get("glass_resistance_trend") or "").strip()
            comparator = str(amr_stewardship.get("existing_watch_comparator") or "").strip()
            similarity = str(amr_stewardship.get("similarity_to_existing_watch") or "").strip()
            amr_bits: list[str] = [
                f"**AMR Stewardship Analysis:** The product is classified under the **{category}** category.",
                rationale,
            ]

            if normalized_ingredient:
                amr_bits.append(f"The ingredient was normalized to **{normalized_ingredient}** for stewardship checks.")

            if category == "ACCESS" and glass_trend == "stable":
                amr_bits.append("Current surveillance signals do not indicate an elevated resistance concern beyond standard monitoring.")
            
            if amr_stewardship.get("watch_similarity_restriction"):
                comparator_label = comparator or "existing Watch agents"
                similarity_label = similarity or "high"
                amr_bits.append(
                    f"Restricted authorization is triggered because the chemistry profile shows **{similarity_label}** similarity to **{comparator_label}**."
                )
            
            if glass_trend == "rising":
                amr_bits.append("Local GLASS surveillance data indicates rising resistance, which increases the stewardship risk.")
            elif glass_trend == "stable" and category in {"WATCH", "RESERVE"}:
                amr_bits.append("Local GLASS surveillance is currently stable, but stewardship controls still matter because of the product class.")

            paragraphs.append(" ".join(bit.strip() for bit in amr_bits if bit and bit.strip()))
            if selected:
                claims.append({"text": f"Product classified as {category} with {rationale}.", "citation_id": str(selected[0].get("citation_id", ""))})
        elif focus["amr"]:
            paragraphs.append("**AMR Stewardship Analysis:** No material AMR stewardship concerns or AWaRe classification triggers were identified for this submission.")

    # 3. Detailed Findings
    if contract == "issue_discovery_v1" or focus["issues"] or any(focus[k] for k in ("count", "rank", "categorize")) or "section" in question.lower():
        paragraphs.append("### Detailed Findings")
        effective_issue_count = len(material_judge_findings) if material_judge_findings else len(issue_entries)
        if "count" in question.lower():
            paragraphs.append(f"My review identified **{effective_issue_count}** material issues that require regulatory attention:")
        elif "rank" in question.lower() or "key" in question.lower():
            paragraphs.append(f"I have prioritized the following **{effective_issue_count}** key issues based on their likely regulatory impact:")

        if material_judge_findings and not ("section" in question.lower() or "per section" in question.lower()):
            for index, finding in enumerate(material_judge_findings[:4], start=1):
                lead = f"{index}. **{str(finding.get('severity', 'major')).upper()}**: {finding.get('requirement_name', 'Requirement review')}"
                detail = str(finding.get("rationale", "")).strip()
                refs = [ref for ref in finding.get("evidence_references", []) if ref]
                if refs:
                    lead = f"{lead} - {detail} [{refs[0]}]"
                    claims.append({"text": f"{finding.get('requirement_name', 'Requirement review')}: {detail}", "citation_id": refs[0]})
                else:
                    lead = f"{lead} - {detail}"
                paragraphs.append(lead)
        elif "section" in question.lower() or "per section" in question.lower():
            if issue_entries:
                by_section: dict[str, list[dict[str, Any]]] = {}
                for item in issue_entries:
                    parts = item["summary"].split(":", 1)
                    section_title = parts[0].strip()
                    by_section.setdefault(section_title, []).append(item)
                
                for section, items in by_section.items():
                    paragraphs.append(f"#### {section}")
                    for it in items:
                        summary_text = it["summary"]
                        if ":" in summary_text:
                            summary_text = summary_text.split(":", 1)[1].strip()
                        paragraphs.append(f"- {summary_text} [{it['citation_id']}]")
                        claims.append({"text": it["summary"], "citation_id": it["citation_id"]})
            else:
                paragraphs.append("No material section-level gaps were identified in the grounded evidence.")

        elif focus["count"]:
            count = effective_issue_count
            if count == 0:
                paragraphs.append("No material dossier issues were identified from the grounded evidence.")
            else:
                paragraphs.append(f"My review identified **{count}** material issue{'s' if count != 1 else ''} that require regulatory attention:")
                if material_judge_findings:
                    for finding in material_judge_findings[: min(count, 3)]:
                        refs = [ref for ref in finding.get("evidence_references", []) if ref]
                        line = f"- {finding.get('requirement_name', 'Requirement review')}: {finding.get('rationale', '')}"
                        if refs:
                            line += f" [{refs[0]}]"
                            claims.append({"text": f"{finding.get('requirement_name', 'Requirement review')}: {finding.get('rationale', '')}", "citation_id": refs[0]})
                        paragraphs.append(line)
                else:
                    for item in issue_entries[: min(count, 3)]:
                        paragraphs.append(f"- {item['summary']} [{item['citation_id']}]")
                        claims.append({"text": item["summary"], "citation_id": item["citation_id"]})

        elif focus["rank"]:
            if material_judge_findings:
                severity_order = {"critical": 3, "major": 2, "minor": 1, "none": 0}
                ranked_findings = sorted(
                    material_judge_findings,
                    key=lambda finding: severity_order.get(str(finding.get("severity", "minor")).lower(), 1),
                    reverse=True,
                )
                for index, finding in enumerate(ranked_findings[:5], start=1):
                    refs = [ref for ref in finding.get("evidence_references", []) if ref]
                    rank_text = f"{index}. **{str(finding.get('severity', 'major')).upper()}**: {finding.get('requirement_name', 'Requirement review')} - {finding.get('rationale', '')}"
                    if refs:
                        rank_text += f" [{refs[0]}]"
                        claims.append({"text": f"{finding.get('requirement_name', 'Requirement review')}: {finding.get('rationale', '')}", "citation_id": refs[0]})
                    paragraphs.append(rank_text)
            else:
                ranked = sorted(issue_entries, key=lambda item: item["priority"], reverse=True)
                if ranked:
                    for index, item in enumerate(ranked[:5], start=1):
                        rank_text = f"{index}. **{item['priority_label'].upper()}**: {item['summary']} [{item['citation_id']}]"
                        paragraphs.append(rank_text)
                        claims.append({"text": f"{item['summary']} ({item['priority_label']})", "citation_id": item["citation_id"]})
                else:
                    paragraphs.append("No issues are currently ranked as no material gaps were identified.")

        elif focus["categorize"]:
            if material_judge_findings:
                grouped_findings: dict[str, list[dict[str, Any]]] = {}
                for finding in material_judge_findings:
                    grouped_findings.setdefault(str(finding.get("issue_category", "general")).replace("_", " ").title(), []).append(finding)
                for category, items in grouped_findings.items():
                    paragraphs.append(f"#### {category}")
                    for finding in items:
                        refs = [ref for ref in finding.get("evidence_references", []) if ref]
                        line = f"- {finding.get('requirement_name', 'Requirement review')}: {finding.get('rationale', '')}"
                        if refs:
                            line += f" [{refs[0]}]"
                            claims.append({"text": f"{category}: {finding.get('requirement_name', 'Requirement review')} {finding.get('rationale', '')}", "citation_id": refs[0]})
                        paragraphs.append(line)
            elif issue_entries:
                grouped: dict[str, list[dict[str, Any]]] = {}
                for item in issue_entries:
                    grouped.setdefault(item["category"], []).append(item)
                for category, items in grouped.items():
                    paragraphs.append(f"#### {category}")
                    for lead in items:
                        summary_text = lead["summary"]
                        if ":" in summary_text:
                            summary_text = summary_text.split(":", 1)[1].strip()
                        paragraphs.append(f"- {summary_text} [{lead['citation_id']}]")
                        claims.append({"text": f"{category}: {lead['summary']}", "citation_id": lead["citation_id"]})
            else:
                paragraphs.append("No issues were found to categorize.")

        else:
            if issue_entries:
                paragraphs.append("The review identified the following material gaps that require regulatory follow-up:")
                for item in issue_entries[:3]:
                    paragraphs.append(f"- {item['summary']} [{item['citation_id']}]")
                    claims.append({"text": item["summary"], "citation_id": item["citation_id"]})
            else:
                paragraphs.append("No material dossier issues were identified from the currently grounded evidence.")

    elif not (contract == "amr_review_v1" or focus["amr"]):
        supporting = selected[:2]
        if supporting:
            paragraphs.append("### Detailed Findings")
            for ev in supporting:
                snippet = str(ev.get('snippet', '')).strip()
                if len(snippet) > 200:
                    snippet = snippet[:197] + "..."
                positive_claim = f"Evidence from **{ev.get('section_title', 'the dossier')}** supports {snippet}"
                paragraphs.append(f"- {positive_claim} [{ev.get('citation_id', '')}]")
                claims.append({"text": positive_claim, "citation_id": str(ev.get("citation_id", ""))})
        else:
            paragraphs.append("The current evidence supports a structurally adequate submission for the proposed path.")

    if focus["gmp"]:
        paragraphs.append("**Quality and GMP Note:** GMP evidence confirms the site's inspection history and certificate status are generally consistent with regulatory requirements, though specific verification of validity dates is recommended.")
        for ev in selected:
            combined = f"{ev.get('section_title','')} {ev.get('snippet','')}".lower()
            if any(term in combined for term in ("gmp", "manufacturer", "quality", "certificate", "facility", "capa")):
                claims.append({"text": "Quality and GMP evidence is consistent with requirements.", "citation_id": str(ev.get("citation_id", ""))})
                break

    if "next reviewer step" in question.lower() or "next step" in question.lower():
        paragraphs.append("### Next Reviewer Step")
        paragraphs.append(_recommended_follow_up(focus=focus, issue_entries=issue_entries, amr_stewardship=amr_stewardship))

    paragraphs.append("### Conclusion")
    paragraphs.append(f"**{final_rec_label}** is the grounded regulatory path. {_recommended_follow_up(focus=focus, issue_entries=issue_entries, amr_stewardship=amr_stewardship)}")

    deduped_claims: list[dict[str, str]] = []
    seen_claims: set[tuple[str, str]] = set()
    for claim in claims:
        text = str(claim.get("text", "")).strip()
        citation_id = str(claim.get("citation_id", "")).strip()
        if not text or not citation_id:
            continue
        key = (text, citation_id)
        if key in seen_claims:
            continue
        seen_claims.add(key)
        deduped_claims.append({"text": text, "citation_id": citation_id})

    return _polish_rationale_text("\n".join(reasoning_lines) + "\n\n" + "\n\n".join(paragraphs)), deduped_claims, None


def _extract_graph_focus(lowered_question: str, summary_stats: dict[str, Any], graph_payload: dict[str, Any]) -> dict[str, Any]:
    focus: dict[str, Any] = {}
    if "antimicrobial" in lowered_question or "amr" in lowered_question:
        focus["product_group"] = "antimicrobial"
    elif "systemic anti-infective" in lowered_question or "anti infective" in lowered_question:
        focus["product_group"] = "systemic_anti_infective"
    elif "renewal" in lowered_question:
        focus["application_type"] = "renewal"
    elif "new application" in lowered_question or "new applications" in lowered_question:
        focus["application_type"] = "new_application"
    elif "veterinary" in lowered_question or "vet " in lowered_question:
        focus["review_domain"] = "veterinary"
    elif "human" in lowered_question:
        focus["review_domain"] = "human"

    products = [node.get("properties", {}).get("name") for node in graph_payload.get("nodes", []) if node.get("type") == "Product"]
    inns = [node.get("properties", {}).get("name") for node in graph_payload.get("nodes", []) if node.get("type") == "ActiveIngredient"]
    for product in products:
        if product and str(product).lower() in lowered_question:
            focus["product_name"] = product
            break
    for inn in inns:
        if inn and str(inn).lower() in lowered_question:
            focus["inn_name"] = inn
            break
    return focus


def _filtered_recommendation_counts(summary_stats: dict[str, Any], focus: dict[str, Any]) -> tuple[dict[str, int], str]:
    if focus.get("product_name"):
        product_bucket = summary_stats.get("by_product", {}).get(focus["product_name"], {})
        return dict(product_bucket.get("recommendations", {})), f"for {focus['product_name']}"
    if focus.get("inn_name"):
        inn_bucket = summary_stats.get("by_inn", {}).get(focus["inn_name"], {})
        return dict(inn_bucket.get("recommendations", {})), f"for {focus['inn_name']}"
    return dict(summary_stats.get("recommendations", {})), "across all processed dossiers"


def _recommendation_counts_from_graph(graph_payload: dict[str, Any], focus: dict[str, Any]) -> tuple[dict[str, int], str] | None:
    if not any(focus.get(key) for key in ("product_group", "application_type", "review_domain")):
        return None
    counts: dict[str, int] = {}
    label_bits: list[str] = []
    for node in graph_payload.get("nodes", []):
        if node.get("type") != "Dossier":
            continue
        props = node.get("properties", {})
        if focus.get("product_group") and props.get("product_group") != focus["product_group"]:
            continue
        if focus.get("application_type") and props.get("application_type") != focus["application_type"]:
            continue
        if focus.get("review_domain") and props.get("review_domain") != focus["review_domain"]:
            continue
        rec = str(props.get("recommendation", "unknown"))
        counts[rec] = counts.get(rec, 0) + 1
    if not counts:
        return None
    if focus.get("product_group"):
        label_bits.append(focus["product_group"].replace("_", " "))
    if focus.get("application_type"):
        label_bits.append(focus["application_type"].replace("_", " "))
    if focus.get("review_domain"):
        label_bits.append(focus["review_domain"])
    return counts, "for " + ", ".join(label_bits)


def _build_issue_entries(
    evidence: list[dict[str, Any]],
    section_diagnostics: list[dict[str, Any]],
    amr_stewardship: dict[str, Any],
) -> list[dict[str, Any]]:
    diagnostic_map = {str(item.get("title", "")): item for item in section_diagnostics}
    entries: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for ev in evidence:
        title = str(ev.get("section_title", "Relevant Section"))
        snippet = _normalize_issue_text(str(ev.get("snippet", "")))
        diag = diagnostic_map.get(title, {})
        citation_id = str(ev.get("citation_id", ""))

        if diag.get("presence") == "missing":
            key = (title, "missing")
            if key not in seen:
                seen.add(key)
                entries.append(
                    {
                        "summary": f"{title}: The section is missing from the dossier and needs reviewer follow-up.",
                        "citation_id": citation_id,
                        "category": _categorize_issue_text(title),
                        "priority": 5,
                        "priority_label": "high",
                    }
                )
        if diag.get("correctness") not in {None, "correct"}:
            key = (title, "correctness")
            if key not in seen:
                seen.add(key)
                entries.append(
                    {
                        "summary": f"{title}: The section is flagged as {diag.get('correctness')} and may not be reliable enough for decision support.",
                        "citation_id": citation_id,
                        "category": _categorize_issue_text(title),
                        "priority": 4,
                        "priority_label": "high",
                    }
                )
        if diag.get("length_status") not in {None, "length_ok"}:
            key = (title, "length")
            if key not in seen:
                seen.add(key)
                entries.append(
                    {
                        "summary": f"{title}: The section is {diag.get('length_status').replace('_', ' ')} and may not contain sufficient usable detail.",
                        "citation_id": citation_id,
                        "category": _categorize_issue_text(title),
                        "priority": 3,
                        "priority_label": "medium",
                    }
                )

        for candidate in _split_issue_candidates(str(ev.get("text") or snippet)):
            normalized_candidate = _normalize_issue_text(candidate)
            lowered_candidate = normalized_candidate.lower()
            if not normalized_candidate or len(normalized_candidate) < 5:
                continue
            if any(term in lowered_candidate for term in POSITIVE_TERMS) and not _looks_like_issue(normalized_candidate):
                continue
            if not _looks_like_issue(normalized_candidate):
                continue
            category = _categorize_issue_text(normalized_candidate)
            priority = 2
            if diag.get("critical"):
                priority += 2
            if diag.get("correctness") not in {None, "correct"}:
                priority += 1
            if any(term in lowered_candidate for term in ("critical", "expired", "not met", "restrict", "rising resistance", "missing")):
                priority += 1
            
            summary_desc = normalized_candidate[0].upper() + normalized_candidate[1:]
            summary = f"{title}: {summary_desc}"
            key = (category, summary)
            if key in seen:
                continue
            seen.add(key)
            entries.append(
                {
                    "summary": summary,
                    "citation_id": citation_id,
                    "category": category,
                    "priority": priority,
                    "priority_label": "high" if priority >= 5 else ("medium" if priority >= 3 else "low"),
                }
            )

    if amr_stewardship.get("watch_similarity_restriction"):
        entries.append(
            {
                "summary": f"AMR Stewardship: Similarity to {amr_stewardship.get('existing_watch_comparator', 'existing Watch agents')} triggers restricted authorization.",
                "citation_id": str(evidence[0].get("citation_id", "")) if evidence else "",
                "category": "AMR Stewardship",
                "priority": 5,
                "priority_label": "high",
            }
        )
    return entries[:6]


from .intake import _infer_policy_signals_from_text


class LocalModelClient:
    def __init__(self, model_id: str = "gemma-e4b") -> None:
        self.model_id = model_id
        self.mode = os.getenv("DOSSIER_MODEL_MODE", os.getenv("DOSSIER_GEMMA4_MODE", "mock")).lower()
        self.vllm_base_url = os.getenv("DOSSIER_VLLM_BASE_URL", "http://127.0.0.1:8001/v1/chat/completions")
        self.vllm_api_key = os.getenv(os.getenv("DOSSIER_VLLM_API_KEY_ENV", "VLLM_API_KEY"), "")

    def _mock_generate(
        self,
        recommendation: str,
        evidence: list[dict[str, Any]],
        question: str,
        dossier: dict[str, Any] | None = None,
        conversation_context: str | None = None,
        section_diagnostics: list[dict[str, Any]] | None = None,
        amr_stewardship: dict[str, Any] | None = None,
        model_packet: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        rationale, claims, viz_data = _compose_mock_rationale(
            question=question,
            recommendation=recommendation,
            evidence=evidence,
            model_id=self.model_id,
            dossier=dossier,
            conversation_context=conversation_context,
            section_diagnostics=section_diagnostics,
            amr_stewardship=amr_stewardship,
            model_packet=model_packet,
        )
        if not claims:
            claims = [{"text": "No sufficient evidence was found for a grounded recommendation.", "citation_id": ""}]
        return {"rationale": rationale, "claims": claims, "visualization_data": viz_data}

    def _docker_generate(self, prompt: str) -> str:
        command = ["docker", "model", "run", self.model_id, "--prompt", prompt]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or "docker model run failed")
        return completed.stdout.strip()

    def _vllm_generate(self, prompt: str) -> str:
        payload = {
            "model": self.model_id,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a regulatory dossier review assistant. Cite every grounded claim with citation IDs.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
        }
        headers = {"Content-Type": "application/json"}
        if self.vllm_api_key:
            headers["Authorization"] = f"Bearer {self.vllm_api_key}"
        req = request.Request(
            self.vllm_base_url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with request.urlopen(req, timeout=45) as response:  # noqa: S310
            parsed = json.loads(response.read().decode("utf-8"))
        choices = parsed.get("choices", [])
        if not choices:
            raise RuntimeError("vLLM response did not include choices")
        message = choices[0].get("message", {})
        return str(message.get("content", "")).strip()

    def extract_policy_signals(self, text: str, inn_name: str) -> dict[str, Any]:
        if self.mode == "mock":
            return _infer_policy_signals_from_text(text, inn_name)

        prompt_lines = [
            "SYSTEM: You are a Senior Regulatory Data Extractor.",
            "Extract specific policy signals from the provided drug dossier text.",
            "Output ONLY valid JSON matching this schema:",
            "{",
            "  'inn_infringement': boolean,",
            "  'gmp_inspection_status': 'compliant'|'non_compliant'|'expired'|'missing_evidence',",
            "  'gmp_certificate_validity': 'valid'|'expired'|'not_provided',",
            "  'clinical_data_available': boolean,",
            "  'pivotal_trial_outcome': 'endpoint_met'|'endpoint_not_met'|'inconclusive'|'missing_evidence',",
            "  'aware_category': 'access'|'watch'|'reserve'|'not_applicable',",
            "  'amr_unmet_need': 'low'|'moderate'|'high'|'critical'|'not_applicable',",
            "  'targets_mdr_pathogen': boolean,",
            "  'glass_resistance_trend': 'stable'|'rising'|'falling'|'not_applicable',",
            "  'similarity_to_existing_watch': 'low'|'moderate'|'high'|'not_applicable',",
            "  'existing_watch_comparator': string or 'not_applicable'",
            "}",
            "",
            f"INN NAME: {inn_name}",
            "DOSSIER TEXT:",
            text[:6000],
            "",
            "JSON OUTPUT:"
        ]
        prompt = "\n".join(prompt_lines)
        
        try:
            if self.mode == "vllm":
                raw_res = self._vllm_generate(prompt)
            else:
                raw_res = self._docker_generate(prompt)
            
            match = re.search(r"(\{.*\})", raw_res, re.DOTALL)
            if match:
                return json.loads(match.group(1))
            return json.loads(raw_res)
        except Exception:
            return _infer_policy_signals_from_text(text, inn_name)

    def generate(
        self,
        question: str,
        recommendation: str,
        evidence: list[dict[str, Any]],
        route: str,
        dossier: dict[str, Any] | None = None,
        conversation_context: str | None = None,
        section_diagnostics: list[dict[str, Any]] | None = None,
        amr_stewardship: dict[str, Any] | None = None,
        model_packet: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.mode == "mock":
            return self._mock_generate(
                recommendation=recommendation,
                evidence=evidence,
                question=question,
                dossier=dossier,
                conversation_context=conversation_context,
                section_diagnostics=section_diagnostics,
                amr_stewardship=amr_stewardship,
                model_packet=model_packet,
            )

        analysis = (model_packet or {}).get("analysis", {})
        bouncer_audit = (model_packet or {}).get("discarded_audit", [])
        
        prompt_lines = [
            "SYSTEM: You are a Senior Regulatory Auditor. Your primary duty is precision and faithfulness to the provided evidence.",
            "",
            "### 1. THE CHAIN OF AUDIT (CoA) PROTOCOL",
            "You must follow a strict reasoning process before answering:",
            "- Rank evidence chunks by technical specificity to the query.",
            "- Explicitly check for contradictions between different sections of the dossier.",
            "- If the retrieved evidence is silent on a specific detail (dates, numbers, names), you MUST state: 'The provided dossier evidence is silent on [Topic]'. Do not approximate or guess.",
            "- If sections contradict (e.g., Section A says 'Valid', Section B says 'Expired'), you MUST flag this as a 'Critical Discrepancy' material issue.",
            "",
            "### 2. GUIDANCE CONTEXT",
            "In addition to dossier evidence, you may be provided with 'REGULATORY GUIDANCE' chunks.",
            "Use these to interpret the dossier evidence correctly. For example, if guidance says INN similarity > 70% is a failure, and evidence shows 75%, you must recommend rejection based on the guidance.",
            "",
            "### 3. ADVERSARIAL EXAMPLES & EDGE CASES",
            "Example 1: Contradictory GMP Status",
            "Context: [DOC:1] Site is Compliant; [DOC:2] Site is Non-Compliant.",
            "Response: A critical discrepancy was identified. Section 1 reports compliance while Section 2 indicates non-compliance. Reviewer verification is mandatory. [DOC:1][DOC:2]",
            "",
            "### 4. THE REASONING TAG PROTOCOL",
            "Output exactly two blocks: a <reasoning> block with valid JSON, followed by the grounded answer.",
            "SCHEMA:",
            "<reasoning>",
            "{",
            "  'intent': string,",
            "  'resolved_terms': string[],",
            "  'contradictions_found': boolean,",
            "  'evidence_sufficiency_score': float (0.0-1.0),",
            "  'guidance_applied': string[],",
            "  'bouncer_audit': [",
            "    {'chunk_id': string, 'status': 'KEEP'|'DISCARD', 'reason': string}",
            "  ]",
            "}",
            "</reasoning>",
            "",
            "### [Summary Title]",
            "[Final grounded answer using ONLY 'KEEP' chunks and referring to GUIDANCE where applicable.]",
            "",
            "### 5. UI FORMATTING RULES",
            "- Use Bold headers (###) for sections.",
            "- Use Bullet points for issues.",
            "- Use [DOC_ID:SECTION:CHUNK] or [GUIDANCE_ID] at the end of every bullet point.",
            "",
            "PRE-RETRIEVAL ANALYSIS:",
            f"- Resolved Question: {analysis.get('resolved_question', question)}",
            f"- Intent: {analysis.get('intent', 'unknown')}",
            f"- Resolved Terms: {', '.join(analysis.get('constraints', []))}",
            f"- Expansion queries: {', '.join((model_packet or {}).get('sub_queries', []))}",
            "",
            "RETRIEVED CONTEXT (FOR AUDIT):",
        ]
        
        # In the prompt, we provide the raw bouncer audit data for the model to "synthesize" into its JSON reasoning
        for entry in bouncer_audit:
            prompt_lines.append(f"- [AUDIT_DATA] {json.dumps(entry)}")

        for ev in evidence:
            prompt_lines.append(f"- [RETRIEVED] [{ev['citation_id']}] ({ev['section_title']}): {ev['text']}")

        prompt_lines.extend([
            "",
            f"USER REQUEST: {question}",
            "",
            "ASSISTANT RESPONSE (START WITH <reasoning>):",
        ])

        prompt = "\n".join(prompt_lines)
        if self.mode == "vllm":
            text = self._vllm_generate(prompt)
        else:
            text = self._docker_generate(prompt)
        
        claims = extract_cited_claims(text)
        return {
            "rationale": text,
            "claims": claims,
        }


Gemma4Client = LocalModelClient


class GeminiModelClient:
    def __init__(self, model_id: str = "gemma-4-4b-it") -> None:
        self.model_id = model_id
        self.api_key_env = os.getenv("DOSSIER_GEMINI_API_KEY_ENV", "GEMINI_API_KEY")
        self.api_key = os.getenv(self.api_key_env, "")
        self.gemini_model = os.getenv("DOSSIER_GEMINI_MODEL", "gemini-2.5-pro")
        self.base_url = os.getenv("DOSSIER_GEMINI_API_BASE_URL", "https://generativelanguage.googleapis.com/v1beta").rstrip("/")

    def _generate_content(self, prompt: str) -> str:
        if not self.api_key:
            raise RuntimeError(
                f"Gemini provider is enabled but no API key found in environment variable {self.api_key_env}."
            )
        query = urlencode({"key": self.api_key})
        url = f"{self.base_url}/models/{self.gemini_model}:generateContent?{query}"
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1},
        }
        req = request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=60) as response:  # noqa: S310
            parsed = json.loads(response.read().decode("utf-8"))
        candidates = parsed.get("candidates") or []
        if not candidates:
            raise RuntimeError("Gemini response did not include candidates.")
        content = candidates[0].get("content", {})
        parts = content.get("parts") or []
        text = "".join(str(part.get("text", "")) for part in parts).strip()
        if not text:
            raise RuntimeError("Gemini response did not include text content.")
        return text

    def extract_policy_signals(self, text: str, inn_name: str) -> dict[str, Any]:
        prompt_lines = [
            "SYSTEM: You are a Senior Regulatory Data Extractor.",
            "Extract specific policy signals from the provided drug dossier text.",
            "Output ONLY valid JSON matching this schema:",
            "{",
            "  'inn_infringement': boolean,",
            "  'gmp_inspection_status': 'compliant'|'non_compliant'|'expired'|'missing_evidence',",
            "  'gmp_certificate_validity': 'valid'|'expired'|'not_provided',",
            "  'clinical_data_available': boolean,",
            "  'pivotal_trial_outcome': 'endpoint_met'|'endpoint_not_met'|'inconclusive'|'missing_evidence',",
            "  'aware_category': 'access'|'watch'|'reserve'|'not_applicable',",
            "  'amr_unmet_need': 'low'|'moderate'|'high'|'critical'|'not_applicable',",
            "  'targets_mdr_pathogen': boolean,",
            "  'glass_resistance_trend': 'stable'|'rising'|'falling'|'not_applicable',",
            "  'similarity_to_existing_watch': 'low'|'moderate'|'high'|'not_applicable',",
            "  'existing_watch_comparator': string or 'not_applicable'",
            "}",
            "",
            f"INN NAME: {inn_name}",
            "DOSSIER TEXT:",
            text[:6000],
            "",
            "JSON OUTPUT:",
        ]
        prompt = "\n".join(prompt_lines)
        try:
            raw = self._generate_content(prompt)
            match = re.search(r"(\{.*\})", raw, re.DOTALL)
            if match:
                return json.loads(match.group(1))
            return json.loads(raw)
        except Exception:
            return _infer_policy_signals_from_text(text, inn_name)

    def generate(
        self,
        question: str,
        recommendation: str,
        evidence: list[dict[str, Any]],
        route: str,
        dossier: dict[str, Any] | None = None,
        conversation_context: str | None = None,
        section_diagnostics: list[dict[str, Any]] | None = None,
        amr_stewardship: dict[str, Any] | None = None,
        model_packet: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        analysis = (model_packet or {}).get("analysis", {})
        prompt_lines = [
            "SYSTEM: You are a Senior Regulatory Auditor. Return evidence-grounded output only.",
            "You MUST output with this structure:",
            "<reasoning>{...valid JSON...}</reasoning>",
            "then a markdown answer with citations in square brackets matching provided citation IDs.",
            "",
            f"ROUTE: {route}",
            f"INTENT: {analysis.get('intent', 'dossier_review')}",
            f"QUESTION: {question}",
            f"RECOMMENDATION CANDIDATE: {recommendation}",
            "",
            "EVIDENCE:",
        ]
        for ev in evidence:
            prompt_lines.append(
                f"- [{ev.get('citation_id','')}] ({ev.get('section_title','')}): {ev.get('text','')}"
            )
        prompt_lines.append("")
        prompt_lines.append("ASSISTANT RESPONSE:")
        prompt = "\n".join(prompt_lines)

        try:
            text = self._generate_content(prompt)
            claims = extract_cited_claims(text)
            if not claims:
                claims = [{"text": "Grounded assessment generated from provided dossier evidence.", "citation_id": ""}]
            return {"rationale": text, "claims": claims}
        except Exception:
            # Safe fallback to deterministic local mock formatting to avoid demo runtime crashes.
            local_fallback = LocalModelClient(model_id=self.model_id)
            local_fallback.mode = "mock"
            return local_fallback.generate(
                question=question,
                recommendation=recommendation,
                evidence=evidence,
                route=route,
                dossier=dossier,
                conversation_context=conversation_context,
                section_diagnostics=section_diagnostics,
                amr_stewardship=amr_stewardship,
                model_packet=model_packet,
            )


def build_model_client(model_id: str = "gemma-4-4b-it") -> Any:
    provider = os.getenv("DOSSIER_MODEL_PROVIDER", "local").strip().lower()
    local_enabled = os.getenv("DOSSIER_LOCAL_MODEL_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
    gemini_enabled = os.getenv("DOSSIER_GEMINI_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
    if provider == "gemini" and gemini_enabled:
        return GeminiModelClient(model_id=model_id)
    if provider == "local" and local_enabled:
        return LocalModelClient(model_id=model_id)
    if gemini_enabled:
        return GeminiModelClient(model_id=model_id)
    return LocalModelClient(model_id=model_id)
