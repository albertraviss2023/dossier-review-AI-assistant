from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class GraphNode:
    id: str
    type: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphEdge:
    source: str
    target: str
    type: str
    properties: dict[str, Any] = field(default_factory=dict)


class KnowledgeGraph:
    def __init__(self, dossiers: list[dict[str, Any]], lifecycle_by_dossier: dict[str, Any] | None = None) -> None:
        self.nodes: dict[str, GraphNode] = {}
        self.edges: list[GraphEdge] = []
        self._build_graph(dossiers, lifecycle_by_dossier or {})

    @staticmethod
    def _derive_product_group(dossier: dict[str, Any]) -> str:
        policy_signals = dossier.get("policy_signals", {})
        if policy_signals.get("aware_category") and policy_signals.get("aware_category") != "not_applicable":
            return "antimicrobial"
        atc_code = str(dossier.get("product", {}).get("atc_code", ""))
        if atc_code.startswith("J"):
            return "systemic_anti_infective"
        return "other_product"

    @staticmethod
    def _derive_application_type(dossier: dict[str, Any]) -> str:
        text_parts = [
            str(dossier.get("dossier_id", "")),
            str(dossier.get("quality_summary", "")),
            str(dossier.get("clinical_details", "")),
        ]
        for section in dossier.get("sections", []):
            text_parts.append(str(section.get("title", "")))
            text_parts.append(str(section.get("text", ""))[:240])
        lowered = " ".join(text_parts).lower()
        if any(term in lowered for term in ("renewal", "renew", "re-registration", "re registration")):
            return "renewal"
        return "new_application"

    @staticmethod
    def _derive_review_domain(dossier: dict[str, Any]) -> str:
        text_parts = [
            str(dossier.get("product", {}).get("product_name", "")),
            str(dossier.get("product", {}).get("inn_name", "")),
            str(dossier.get("quality_summary", "")),
            str(dossier.get("clinical_details", "")),
        ]
        lowered = " ".join(text_parts).lower()
        if any(term in lowered for term in ("vet", "veterinary", "animal", "livestock", "canine", "bovine", "poultry")):
            return "veterinary"
        return "human"

    def _build_graph(self, dossiers: list[dict[str, Any]], lifecycle_by_dossier: dict[str, Any]) -> None:
        for dossier in dossiers:
            dossier_id = str(dossier.get("dossier_id"))
            sub_date = dossier.get("submission_date", "unknown")
            rec = dossier.get("labels", {}).get("holistic_policy_decision", "unknown")
            product_group = self._derive_product_group(dossier)
            application_type = self._derive_application_type(dossier)
            review_domain = self._derive_review_domain(dossier)
            policy_signals = dossier.get("policy_signals", {})
            aware = policy_signals.get("aware_category")
            lifecycle = lifecycle_by_dossier.get(dossier_id, {})
            review_obs = lifecycle.get("latest_review_observation", {}) if isinstance(lifecycle, dict) else {}
            latest_issues = list(review_obs.get("issue_tags", [])) if isinstance(review_obs, dict) else []
            latest_recommendation = str(review_obs.get("recommendation", "")) if isinstance(review_obs, dict) else ""
            latest_confidence = float(review_obs.get("confidence", 0.0) or 0.0) if isinstance(review_obs, dict) else 0.0
            assigned_reviewer = str(lifecycle.get("assigned_reviewer", "")) if isinstance(lifecycle, dict) else ""
            lifecycle_status = str(lifecycle.get("status", "open")) if isinstance(lifecycle, dict) else "open"
            final_decision = str(lifecycle.get("final_decision", "")) if isinstance(lifecycle, dict) else ""

            # Dossier Node
            self.nodes[dossier_id] = GraphNode(
                id=dossier_id,
                type="Dossier",
                properties={
                    "submission_date": sub_date,
                    "recommendation": rec,
                    "country": dossier.get("country"),
                    "product_group": product_group,
                    "application_type": application_type,
                    "review_domain": review_domain,
                    "aware_category": aware,
                    "lifecycle_status": lifecycle_status,
                    "assigned_reviewer": assigned_reviewer or None,
                    "latest_recommendation": latest_recommendation or None,
                    "latest_confidence": latest_confidence,
                    "latest_issue_count": len(latest_issues),
                    "final_decision": final_decision or None,
                }
            )

            # Product Node
            product = dossier.get("product", {})
            product_name = (
                product.get("product_name")
                or dossier.get("product_name")
            )
            inn_name = (
                product.get("inn_name")
                or dossier.get("inn")
                or dossier.get("inn_name")
            )
            dosage_form = product.get("dosage_form") or dossier.get("dosage_form")
            strength = product.get("strength") or dossier.get("strength")
            atc_code = product.get("atc_code") or dossier.get("atc_code")
            if product_name:
                product_id = f"product:{product_name}"
                if product_id not in self.nodes:
                    self.nodes[product_id] = GraphNode(
                        id=product_id,
                        type="Product",
                        properties={"name": product_name, "inn": inn_name, "dosage_form": dosage_form, "strength": strength}
                    )
                self.edges.append(GraphEdge(source=dossier_id, target=product_id, type="HAS_PRODUCT"))
            if inn_name:
                inn_id = f"inn:{inn_name}"
                if inn_id not in self.nodes:
                    self.nodes[inn_id] = GraphNode(
                        id=inn_id,
                        type="ActiveIngredient",
                        properties={"name": inn_name, "atc_code": atc_code}
                    )
                self.edges.append(GraphEdge(source=dossier_id, target=inn_id, type="HAS_ACTIVE_INGREDIENT"))

            # Organization Node
            org = dossier.get("organization", {})
            applicant = (
                org.get("applicant")
                or org.get("applicant_name")
                or dossier.get("applicant_name")
                or dossier.get("applicant")
            )
            manufacturer = (
                org.get("manufacturer")
                or org.get("manufacturer_name")
                or dossier.get("manufacturer_name")
                or dossier.get("manufacturer")
            )
            facility_country = (
                org.get("facility_country")
                or dossier.get("manufacturer_country")
                or dossier.get("facility_country")
            )
            if applicant:
                org_id = f"org:{applicant}"
                if org_id not in self.nodes:
                    self.nodes[org_id] = GraphNode(
                        id=org_id,
                        type="Organization",
                        properties={"name": applicant}
                    )
                self.edges.append(GraphEdge(source=dossier_id, target=org_id, type="SUBMITTED_BY"))
            if manufacturer:
                mfg_id = f"manufacturer:{manufacturer}"
                if mfg_id not in self.nodes:
                    self.nodes[mfg_id] = GraphNode(
                        id=mfg_id,
                        type="Manufacturer",
                        properties={"name": manufacturer, "facility_country": facility_country},
                    )
                self.edges.append(GraphEdge(source=dossier_id, target=mfg_id, type="MANUFACTURED_BY"))

            country = dossier.get("country")
            if country:
                country_id = f"country:{country}"
                if country_id not in self.nodes:
                    self.nodes[country_id] = GraphNode(
                        id=country_id,
                        type="Country",
                        properties={"name": country}
                    )
                self.edges.append(GraphEdge(source=dossier_id, target=country_id, type="SUBMITTED_IN"))
            try:
                year = datetime.fromisoformat(str(sub_date)).year
                year_id = f"year:{year}"
                if year_id not in self.nodes:
                    self.nodes[year_id] = GraphNode(id=year_id, type="SubmissionYear", properties={"year": year})
                self.edges.append(GraphEdge(source=dossier_id, target=year_id, type="SUBMITTED_IN_YEAR"))
            except (TypeError, ValueError):
                pass

            group_id = f"group:{product_group}"
            if group_id not in self.nodes:
                self.nodes[group_id] = GraphNode(
                    id=group_id,
                    type="ProductGroup",
                    properties={"name": product_group}
                )
            self.edges.append(GraphEdge(source=dossier_id, target=group_id, type="HAS_PRODUCT_GROUP"))

            app_type_id = f"application:{application_type}"
            if app_type_id not in self.nodes:
                self.nodes[app_type_id] = GraphNode(
                    id=app_type_id,
                    type="ApplicationType",
                    properties={"name": application_type}
                )
            self.edges.append(GraphEdge(source=dossier_id, target=app_type_id, type="HAS_APPLICATION_TYPE"))

            domain_id = f"domain:{review_domain}"
            if domain_id not in self.nodes:
                self.nodes[domain_id] = GraphNode(
                    id=domain_id,
                    type="ReviewDomain",
                    properties={"name": review_domain}
                )
            self.edges.append(GraphEdge(source=dossier_id, target=domain_id, type="HAS_REVIEW_DOMAIN"))

            recommendation_id = f"recommendation:{rec}"
            if recommendation_id not in self.nodes:
                self.nodes[recommendation_id] = GraphNode(
                    id=recommendation_id,
                    type="Recommendation",
                    properties={"name": rec}
                )
            self.edges.append(GraphEdge(source=dossier_id, target=recommendation_id, type="HAS_RECOMMENDATION"))

            # AMR Category Node
            if aware and aware != "not_applicable":
                aware_id = f"aware:{aware}"
                if aware_id not in self.nodes:
                    self.nodes[aware_id] = GraphNode(
                        id=aware_id,
                        type="AMRCategory",
                        properties={"name": aware}
                    )
                self.edges.append(GraphEdge(source=dossier_id, target=aware_id, type="HAS_AMR_CATEGORY"))

            # Violations / Issues
            # We can use policy_signals or section labels for this
            if policy_signals.get("inn_infringement"):
                v_id = "violation:inn_infringement"
                if v_id not in self.nodes:
                    self.nodes[v_id] = GraphNode(id=v_id, type="Violation", properties={"name": "INN Infringement"})
                self.edges.append(GraphEdge(source=dossier_id, target=v_id, type="HAS_VIOLATION"))
            
            if policy_signals.get("gmp_inspection_status") == "non_compliant":
                v_id = "violation:gmp_non_compliant"
                if v_id not in self.nodes:
                    self.nodes[v_id] = GraphNode(id=v_id, type="Violation", properties={"name": "GMP Non-Compliant"})
                self.edges.append(GraphEdge(source=dossier_id, target=v_id, type="HAS_VIOLATION"))

            for issue in latest_issues:
                issue_key = str(issue).strip().lower().replace(" ", "_")
                if not issue_key:
                    continue
                issue_id = f"issue:{issue_key}"
                if issue_id not in self.nodes:
                    self.nodes[issue_id] = GraphNode(
                        id=issue_id,
                        type="ReviewIssue",
                        properties={"name": str(issue), "source": "review_observation"},
                    )
                self.edges.append(GraphEdge(source=dossier_id, target=issue_id, type="HAS_REVIEW_ISSUE"))

            if assigned_reviewer:
                reviewer_id = f"reviewer:{assigned_reviewer}"
                if reviewer_id not in self.nodes:
                    self.nodes[reviewer_id] = GraphNode(
                        id=reviewer_id,
                        type="Reviewer",
                        properties={"username": assigned_reviewer},
                    )
                self.edges.append(GraphEdge(source=dossier_id, target=reviewer_id, type="ASSIGNED_TO"))

    def get_summary_stats(self) -> dict[str, Any]:
        """Returns aggregate stats for trend analysis."""
        stats = {
            "total_dossiers": 0,
            "recommendations": {},
            "aware_categories": {},
            "violations": {},
            "countries": {},
            "product_groups": {},
            "application_types": {},
            "review_domains": {},
            "by_product": {},
            "by_inn": {},
            "trends": {}, # monthly trends
        }
        
        for node in self.nodes.values():
            if node.type == "Dossier":
                stats["total_dossiers"] += 1
                rec = node.properties.get("recommendation")
                stats["recommendations"][rec] = stats["recommendations"].get(rec, 0) + 1
                country = node.properties.get("country") or "unknown"
                stats["countries"][country] = stats["countries"].get(country, 0) + 1
                product_group = node.properties.get("product_group") or "other_product"
                stats["product_groups"][product_group] = stats["product_groups"].get(product_group, 0) + 1
                application_type = node.properties.get("application_type") or "unknown"
                stats["application_types"][application_type] = stats["application_types"].get(application_type, 0) + 1
                review_domain = node.properties.get("review_domain") or "human"
                stats["review_domains"][review_domain] = stats["review_domains"].get(review_domain, 0) + 1
                
                # Trend analysis
                date_str = node.properties.get("submission_date")
                try:
                    dt = datetime.fromisoformat(date_str)
                    month_key = dt.strftime("%Y-%m")
                except (ValueError, TypeError):
                    month_key = "unknown"
                
                if month_key not in stats["trends"]:
                    stats["trends"][month_key] = {"total": 0, "recommendations": {}}
                
                stats["trends"][month_key]["total"] += 1
                stats["trends"][month_key]["recommendations"][rec] = stats["trends"][month_key]["recommendations"].get(rec, 0) + 1

        product_links: dict[str, str] = {}
        inn_links: dict[str, str] = {}
        
        for edge in self.edges:
            if edge.type == "HAS_AMR_CATEGORY":
                target_node = self.nodes[edge.target]
                aware = target_node.properties.get("name")
                stats["aware_categories"][aware] = stats["aware_categories"].get(aware, 0) + 1
            elif edge.type == "HAS_VIOLATION":
                target_node = self.nodes[edge.target]
                violation = target_node.properties.get("name")
                stats["violations"][violation] = stats["violations"].get(violation, 0) + 1
            elif edge.type == "HAS_PRODUCT":
                product_links[edge.source] = edge.target
            elif edge.type == "HAS_ACTIVE_INGREDIENT":
                inn_links[edge.source] = edge.target

        for dossier_id, product_id in product_links.items():
            product_name = self.nodes[product_id].properties.get("name") or "unknown"
            dossier = self.nodes.get(dossier_id)
            if not dossier:
                continue
            rec = dossier.properties.get("recommendation", "unknown")
            bucket = stats["by_product"].setdefault(product_name, {"total": 0, "recommendations": {}})
            bucket["total"] += 1
            bucket["recommendations"][rec] = bucket["recommendations"].get(rec, 0) + 1

        for dossier_id, inn_id in inn_links.items():
            inn_name = self.nodes[inn_id].properties.get("name") or "unknown"
            dossier = self.nodes.get(dossier_id)
            if not dossier:
                continue
            rec = dossier.properties.get("recommendation", "unknown")
            bucket = stats["by_inn"].setdefault(inn_name, {"total": 0, "recommendations": {}})
            bucket["total"] += 1
            bucket["recommendations"][rec] = bucket["recommendations"].get(rec, 0) + 1
                
        return stats

    def to_json(self) -> dict[str, Any]:
        return {
            "nodes": [
                {"id": n.id, "type": n.type, "properties": n.properties}
                for n in self.nodes.values()
            ],
            "edges": [
                {"source": e.source, "target": e.target, "type": e.type, "properties": e.properties}
                for e in self.edges
            ]
        }
