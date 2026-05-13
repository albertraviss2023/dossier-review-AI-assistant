from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


REVIEW_INTENT = "dossier_review"
FOLLOWUP_INTENT = "dossier_followup"
CHAT_ONLY_INTENT = "chat_only"
ISSUE_DISCOVERY_INTENT = "issue_discovery"
WIKI_GUIDANCE_INTENT = "wiki_guidance"
AMR_INTENT = "amr_stewardship"
REPORT_INTENT = "report_generation"
MIXED_INTENT = "mixed_compare_synthesize"
VISUALIZATION_INTENT = "visualization"

# Analyst Layer Intent Buckets
TECHNICAL_LOOKUP = "technical_acronym_lookup"
COMPARATIVE = "comparative_versus"
HISTORICAL_TREND = "historical_trend"
POLICY_GUIDANCE = "policy_guidance"


class GlossaryTool:
    def __init__(self) -> None:
        self.glossary = {
            "AMR": "Antimicrobial Resistance (the ability of microbes to resist the effects of drugs)",
            "SSMR": "Stewardship-Supported Market Review (a specialized review path for antibiotics)",
            "MDR": "Multi-Drug Resistant (pathogens resistant to multiple antimicrobial classes)",
            "AWaRe": "Access, Watch, Reserve (WHO antibiotic classification framework)",
            "GLASS": "Global Antimicrobial Resistance and Use Surveillance System (WHO)",
            "GMP": "Good Manufacturing Practice",
            "CMC": "Chemistry, Manufacturing, and Controls",
            "INN": "International Nonproprietary Name",
            "PQS": "Pharmaceutical Quality System",
        }
        self.typo_map = {
            "ARM": "AMR",
            "AWRE": "AWaRe",
            "AWARE": "AWaRe",
            "GLAS": "GLASS",
            "GPM": "GMP",
            "CCM": "CMC",
            "IN": "INN",
        }

    def resolve(self, query: str) -> str:
        resolved_query = query
        # Fix common acronym typos first
        for typo, correction in self.typo_map.items():
            pattern = re.compile(rf"\b{re.escape(typo)}\b", re.IGNORECASE)
            resolved_query = pattern.sub(correction, resolved_query)
            
        for acronym, definition in self.glossary.items():
            # Use regex for word boundary matching
            pattern = re.compile(rf"\b{re.escape(acronym)}\b", re.IGNORECASE)
            if pattern.search(resolved_query):
                resolved_query = pattern.sub(f"{acronym} ({definition})", resolved_query)
        return resolved_query


@dataclass(frozen=True)
class ContextScope:
    include_conversation: bool = False
    include_dossier: bool = False
    include_review_state: bool = False
    include_wiki: bool = False
    include_external: bool = False
    llm_only: bool = False


@dataclass(frozen=True)
class RoutePlan:
    intent: str
    response_contract: str
    context_scope: ContextScope
    retrieval_domains: tuple[str, ...]
    should_decompose_query: bool
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ModelPacket:
    packet_version: str
    intent: str
    response_contract: str
    active_workspace: str
    reviewer_question: str
    active_dossier_id: str | None
    source_boundaries: dict[str, str]
    blocks: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class QueryRewritePlan:
    original_question: str
    rewritten_question: str
    intent: str
    workspace: str
    hard_constraints: tuple[str, ...] = ()
    expansion_terms: tuple[str, ...] = ()
    metadata_filter: dict[str, Any] = field(default_factory=dict)
    rewrite_notes: tuple[str, ...] = ()


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


INTENT_KEYWORDS = {
    REPORT_INTENT: ("report", "download", "send report", "generate report", "export", "raport", "repurt"),
    MIXED_INTENT: ("compare", "versus", "vs ", "using guidance", "with policy", "cross-reference", "compere", "versos"),
    WIKI_GUIDANCE_INTENT: ("guidance", "policy", "wiki", "playbook", "what guidance", "sop", "guidence", "polocy", "wikkie"),
    AMR_INTENT: ("amr", "aware", "glass", "stewardship", "resistance", "chemistry", "similarity", "stwerdship", "resistnce", "chemestry"),
    REVIEW_INTENT: ("review", "recommend", "regulatory action", "summarize", "assessment", "reccomend", "sumarize", "reviw"),
    ISSUE_DISCOVERY_INTENT: ("find issues", "issue", "contradict", "gap", "rank", "categorize", "discrepancy", "isue", "isues", "contredict"),
    FOLLOWUP_INTENT: ("continue", "follow up", "remaining", "previous", "prior", "contineu", "folow up"),
    VISUALIZATION_INTENT: ("graph", "plot", "chart", "pie chart", "bar graph", "visualize", "distribution", "graf", "plat", "chrt"),
    
    # Analyst Layer Keywords
    TECHNICAL_LOOKUP: ("what is", "define", "definition", "acronym", "meaning", "lookup", "definiton", "accronym"),
    COMPARATIVE: ("versus", "vs ", "compared", "difference", "distinguish", "diffrence", "distingish"),
    HISTORICAL_TREND: ("trend", "history", "historical", "over time", "evolution", "trnd", "histry"),
    POLICY_GUIDANCE: ("guidance", "policy", "framework", "standard", "procedure", "rule", "guidence", "polocy"),
}

GREETINGS = {
    "hi", "hello", "hey", "hi friend", "hello friend", "hey friend", 
    "good morning", "good afternoon", "greetings", "how are you", 
    "how r u", "how are you today", "how r u today", "what's up", 
    "whats up", "yo", "hi there", "hello there",
    "hie", "helo", "hay", "howdy"
}

DOMAIN_PHRASE_CORRECTIONS: tuple[tuple[str, str], ...] = (
    (r"\bhi fried\b", "hi friend"),
    (r"\breviwer\b", "reviewer"),
    (r"\bguidnce\b", "guidance"),
    (r"\bpoicy\b", "policy"),
    (r"\bpolciy\b", "policy"),
    (r"\bwikkie\b", "wiki"),
    (r"\bstablity\b", "stability"),
    (r"\bshelf lif\b", "shelf life"),
    (r"\bjustifcation\b", "justification"),
    (r"\bexpirry\b", "expiry"),
    (r"\bauthoriztion\b", "authorization"),
    (r"\bdossir\b", "dossier"),
    (r"\bisues\b", "issues"),
    (r"\bcontrdictions\b", "contradictions"),
)


QUERY_EXPANSION_LIBRARY: dict[str, tuple[str, ...]] = {
    "stability": ("shelf life", "storage conditions", "accelerated studies", "long-term studies"),
    "gmp": ("good manufacturing practice", "inspection", "certificate validity", "capa"),
    "clinical": ("pivotal trial", "endpoint", "efficacy", "benefit-risk"),
    "contradiction": ("discrepancy", "mismatch", "inconsistency", "conflict"),
    "missing evidence": ("not provided", "incomplete", "omission", "absent evidence"),
    "amr": ("antimicrobial resistance", "AWaRe", "GLASS", "stewardship"),
    "manufacturer": ("manufacturing site", "facility", "quality system", "inspection history"),
    "origin": ("country of origin", "source country", "manufacturing location"),
    "product": ("medicine", "submission product", "inn", "active ingredient"),
}


def normalize_query_text(question: str) -> str:
    normalized = question
    for pattern, replacement in DOMAIN_PHRASE_CORRECTIONS:
        normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bsnd\b", "and", normalized, flags=re.IGNORECASE)
    return " ".join(normalized.split())


def _infer_expansion_terms(question: str, constraints: list[str], intent: str) -> tuple[str, ...]:
    lowered = question.lower()
    expanded: list[str] = []

    def _extend(key: str) -> None:
        expanded.extend(QUERY_EXPANSION_LIBRARY.get(key, ()))

    if "stability" in lowered:
        _extend("stability")
    if any(term in lowered for term in ("gmp", "inspection", "certificate", "manufacturer", "quality")):
        _extend("gmp")
        _extend("manufacturer")
    if any(term in lowered for term in ("clinical", "trial", "endpoint", "efficacy", "benefit-risk", "safety")):
        _extend("clinical")
    if any(term in lowered for term in ("issue", "gap", "missing", "contradict", "discrepancy", "deficiency")):
        _extend("missing evidence")
        _extend("contradiction")
    if any(term in lowered for term in ("amr", "aware", "glass", "stewardship", "resistance")):
        _extend("amr")
    if "Manufacturer" in constraints:
        _extend("manufacturer")
    if "Origin" in constraints:
        _extend("origin")
    if "Product" in constraints:
        _extend("product")

    if intent in {MIXED_INTENT, ISSUE_DISCOVERY_INTENT}:
        _extend("missing evidence")
    if intent == AMR_INTENT:
        _extend("amr")

    deduped: list[str] = []
    seen: set[str] = set()
    for term in expanded:
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(term)
    return tuple(deduped)


def build_query_rewrite_plan(
    *,
    question: str,
    workspace: str = "review",
    has_active_dossier: bool = True,
    has_conversation: bool = False,
) -> QueryRewritePlan:
    glossary = GlossaryTool()
    normalized_question = normalize_query_text(question)
    rewritten = glossary.resolve(normalized_question)
    intent = classify_intent(
        question=rewritten,
        workspace=workspace,
        has_active_dossier=has_active_dossier,
        has_conversation=has_conversation,
    )
    constraints = extract_constraints(rewritten)
    expansion_terms = _infer_expansion_terms(rewritten, constraints, intent)
    metadata_filter: dict[str, Any] = {}
    rewrite_notes: list[str] = []

    if rewritten != question:
        rewrite_notes.append("Expanded or corrected domain acronyms before retrieval planning.")
    if constraints:
        rewrite_notes.append("Extracted hard constraints to narrow retrieval scope.")
    if expansion_terms:
        rewrite_notes.append("Added regulatory and dossier-specific terminology variants for recall.")
    if intent == HISTORICAL_TREND or "approval" in rewritten.lower():
        metadata_filter["category"] = "regulatory_action"
        rewrite_notes.append("Applied regulatory-action filter for trend-oriented retrieval.")

    return QueryRewritePlan(
        original_question=question,
        rewritten_question=rewritten,
        intent=intent,
        workspace=workspace,
        hard_constraints=tuple(constraints),
        expansion_terms=expansion_terms,
        metadata_filter=metadata_filter,
        rewrite_notes=tuple(rewrite_notes),
    )


def classify_intent(*, question: str, workspace: str = "review", has_active_dossier: bool = True, has_conversation: bool = False) -> str:
    lowered = " ".join(question.lower().split())
    # Handle "how are you today?" or "how r u today"
    stripped = lowered.strip("?.!")

    if stripped in GREETINGS or any(g in stripped for g in ("how are you", "how r u")):
        # If it's JUST a greeting or a greeting + how are you
        if len(stripped.split()) <= 4:
            return CHAT_ONLY_INTENT

    # 1. Visualization (highest priority because it can contain 'vs' or 'history' or 'trend')
    if any(kw in lowered for kw in ("graph", "plot", "chart", "pie chart", "bar graph", "visualize", "distribution", "approval trend", "graf", "plat", "chrt")):
        return VISUALIZATION_INTENT

    # 2. Technical/Acronym Lookup
    if any(kw in lowered for kw in ("what is", "define", "definition", "acronym", "meaning", "lookup", "definiton", "accronym")):
        return TECHNICAL_LOOKUP
    
    # 3. Comparative/Versus
    if any(kw in lowered for kw in ("versus", "vs ", "compared", "difference", "distinguish", "diffrence", "distingish")):
        return COMPARATIVE

    if "compare" in lowered and any(kw in lowered for kw in ("guidance", "policy", "external", "stewardship", "who ")):
        return MIXED_INTENT

    # 4. Historical/Trend
    if any(kw in lowered for kw in ("trend", "history", "historical", "over time", "evolution", "trnd", "histry")):
        return HISTORICAL_TREND

    # High-priority workspace-based routing
    if workspace == "wiki":
        return WIKI_GUIDANCE_INTENT
    if workspace == "amr":
        return AMR_INTENT
    if workspace == "issues":
        return ISSUE_DISCOVERY_INTENT

    # 4. Policy/Guidance
    if any(kw in lowered for kw in ("guidance", "policy", "framework", "standard", "procedure", "rule", "guidence", "polocy")):
        return POLICY_GUIDANCE
    if not has_active_dossier and any(
        kw in lowered for kw in ("sop", "tutorial", "how to", "show me how", "workflow", "playbook")
    ):
        return WIKI_GUIDANCE_INTENT

    # Keyword-based scoring (Improved with fuzzy/partial matching)
    scores = {intent: 0 for intent in INTENT_KEYWORDS}
    for intent, keywords in INTENT_KEYWORDS.items():
        for kw in keywords:
            if kw in lowered:
                scores[intent] += 2
            # Check for partial word matches to handle simple typos/suffixes
            elif len(kw) > 4 and kw[:-1] in lowered:
                scores[intent] += 1

    # Sort intents by score
    best_intent = max(scores, key=scores.get)
    if scores[best_intent] > 0:
        # Contextual validation for specific intents
        if best_intent == FOLLOWUP_INTENT and not (has_active_dossier and has_conversation):
            return REVIEW_INTENT if has_active_dossier else CHAT_ONLY_INTENT
        if best_intent in (REVIEW_INTENT, ISSUE_DISCOVERY_INTENT, AMR_INTENT) and not has_active_dossier:
            if any(kw in lowered for kw in ("sop", "tutorial", "how to", "workflow", "guidance", "policy", "playbook")):
                return WIKI_GUIDANCE_INTENT
            return WIKI_GUIDANCE_INTENT if best_intent == AMR_INTENT else CHAT_ONLY_INTENT
        return best_intent

    # Fallback logic
    if has_active_dossier:
        return REVIEW_INTENT
    return CHAT_ONLY_INTENT


def extract_constraints(question: str) -> list[str]:
    """Identify specific entities (Hard Constraints) in the query with typo resilience."""
    constraints: list[str] = []
    lowered = question.lower()

    # Entity patterns with typo allowance
    patterns = {
        "Manufacturer": r"\b(manufactur|maker|producer|facil|manfactur|mfg)\w*\b",
        "Origin": r"\b(origin|source|country|location|orgigin|where from)\b",
        "Product": r"\b(product|drug|medicin|item|ingredient|inn)\w*\b",
        "Submission": r"\b(submiss|dossier|file|case|content)\w*\b",
        "GMP": r"\b(gmp|inspection|quality|certif)\w*\b",
    }

    for entity, pattern in patterns.items():
        if re.search(pattern, lowered):
            constraints.append(entity)

    # Section matching
    section_match = re.search(r"\b(section\s+\d+|module\s+\d+)\b", lowered, re.IGNORECASE)
    if section_match:
        constraints.append(section_match.group(0))

    # Specific regulatory entities/acronyms
    entities = ["MDR", "AWaRe", "GLASS", "RxNorm", "PubChem", "Climatic Zone IV", "Climatic Zone III"]
    for entity in entities:
        if re.search(rf"\b{re.escape(entity)}\b", question, re.IGNORECASE):
            constraints.append(entity)

    return constraints

def plan_context_scope(intent: str, *, workspace: str = "review") -> RoutePlan:
    if intent == CHAT_ONLY_INTENT:
        return RoutePlan(
            intent=intent,
            response_contract="conversational_assistant_v1",
            context_scope=ContextScope(include_conversation=True, llm_only=True),
            retrieval_domains=(),
            should_decompose_query=False,
            notes=("No retrieval required unless the reviewer later brings a dossier or guidance source into scope.",),
        )
    
    # Analyst Layer Scope Planning
    if intent == TECHNICAL_LOOKUP:
        return RoutePlan(
            intent=intent,
            response_contract="technical_lookup_v1",
            context_scope=ContextScope(include_wiki=True),
            retrieval_domains=("knowledge_wiki",),
            should_decompose_query=False,
        )
    if intent == COMPARATIVE:
        return RoutePlan(
            intent=intent,
            response_contract="comparative_analysis_v1",
            context_scope=ContextScope(include_dossier=True, include_wiki=True, include_external=True),
            retrieval_domains=("dossier", "knowledge_wiki", "external"),
            should_decompose_query=True,
        )
    if intent == HISTORICAL_TREND:
        return RoutePlan(
            intent=intent,
            response_contract="trend_analysis_v1",
            context_scope=ContextScope(include_dossier=True, include_review_state=True),
            retrieval_domains=("dossier", "review_state"),
            should_decompose_query=True,
        )
    if intent == POLICY_GUIDANCE:
        return RoutePlan(
            intent=intent,
            response_contract="policy_guidance_v1",
            context_scope=ContextScope(include_wiki=True, include_external=True),
            retrieval_domains=("knowledge_wiki", "external"),
            should_decompose_query=True,
        )

    if intent == VISUALIZATION_INTENT:
        return RoutePlan(
            intent=intent,
            response_contract="visualization_v1",
            context_scope=ContextScope(include_review_state=True),
            retrieval_domains=("review_state",),
            should_decompose_query=False,
        )
    if intent == WIKI_GUIDANCE_INTENT:
        return RoutePlan(
            intent=intent,
            response_contract="wiki_guidance_v1",
            context_scope=ContextScope(include_conversation=True, include_wiki=True, include_review_state=True),
            retrieval_domains=("knowledge_wiki",),
            should_decompose_query=True,
        )
    if intent == AMR_INTENT:
        return RoutePlan(
            intent=intent,
            response_contract="amr_review_v1",
            context_scope=ContextScope(
                include_conversation=True,
                include_dossier=True,
                include_review_state=True,
                include_external=True,
            ),
            retrieval_domains=("dossier", "external"),
            should_decompose_query=True,
        )
    if intent == ISSUE_DISCOVERY_INTENT:
        return RoutePlan(
            intent=intent,
            response_contract="issue_discovery_v1",
            context_scope=ContextScope(include_conversation=True, include_dossier=True, include_review_state=True),
            retrieval_domains=("dossier",),
            should_decompose_query=True,
        )
    if intent == REPORT_INTENT:
        return RoutePlan(
            intent=intent,
            response_contract="review_report_v1",
            context_scope=ContextScope(include_conversation=True, include_dossier=True, include_review_state=True),
            retrieval_domains=("review_state", "dossier"),
            should_decompose_query=False,
        )
    if intent == MIXED_INTENT:
        return RoutePlan(
            intent=intent,
            response_contract="mixed_compare_synthesize_v1",
            context_scope=ContextScope(
                include_conversation=True,
                include_dossier=True,
                include_review_state=True,
                include_wiki=True,
                include_external=True,
            ),
            retrieval_domains=("dossier", "knowledge_wiki", "external"),
            should_decompose_query=True,
        )
    if intent == FOLLOWUP_INTENT:
        return RoutePlan(
            intent=intent,
            response_contract="review_followup_v1",
            context_scope=ContextScope(include_conversation=True, include_dossier=True, include_review_state=True),
            retrieval_domains=("dossier",),
            should_decompose_query=True,
        )
    return RoutePlan(
        intent=REVIEW_INTENT,
        response_contract="dossier_review_v1",
        context_scope=ContextScope(include_conversation=True, include_dossier=True, include_review_state=True),
        retrieval_domains=("dossier",),
        should_decompose_query=True,
    )


def assemble_model_packet(
    *,
    question: str,
    workspace: str,
    route_plan: RoutePlan,
    dossier_id: str | None,
    conversation_context: str = "",
    dossier_hits: list[dict[str, Any]] | None = None,
    wiki_hits: list[dict[str, Any]] | None = None,
    external_context: dict[str, Any] | None = None,
    review_state: dict[str, Any] | None = None,
) -> ModelPacket:
    blocks: dict[str, Any] = {}
    source_boundaries = {
        "conversation": "reviewer_thread_context",
        "dossier": "dossier_submission_evidence",
        "wiki": "curated_reviewer_guidance",
        "external": "source_of_truth_external_evidence",
        "review_state": "current_review_workflow_state",
    }

    if route_plan.context_scope.include_conversation and conversation_context:
        blocks["conversation"] = {"summary": conversation_context}
    elif route_plan.context_scope.include_conversation:
        blocks["conversation"] = {"summary": ""}
    if route_plan.context_scope.include_dossier:
        blocks["dossier"] = {"hits": dossier_hits or []}
    if route_plan.context_scope.include_wiki:
        blocks["wiki"] = {"hits": wiki_hits or []}
    if route_plan.context_scope.include_external:
        blocks["external"] = external_context or {}
    if route_plan.context_scope.include_review_state:
        blocks["review_state"] = review_state or {}

    return ModelPacket(
        packet_version="mcp_router_packet_v1",
        intent=route_plan.intent,
        response_contract=route_plan.response_contract,
        active_workspace=workspace,
        reviewer_question=question,
        active_dossier_id=dossier_id,
        source_boundaries=source_boundaries,
        blocks=blocks,
    )
