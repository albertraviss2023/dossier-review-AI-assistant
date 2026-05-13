from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urljoin, urlparse
from urllib.request import Request, urlopen

from regulatory_mcp_server.app import mcp, settings
from regulatory_mcp_server.schemas import (
    CompareGenericPatientInformationRequest,
    FetchInnovatorPatientInformationRequest,
    PatientInfoSection,
)

from .common import build_tool_envelope, tool_audit


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = PROJECT_ROOT / "regulatory_mcp_server" / "data" / "cached_sources"
LOGGER = logging.getLogger("regulatory_mcp_server.tools.patient_info")

DIMENSION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "indications": ("indication", "used", "treatment"),
    "dosage": ("dose", "dosage", "take", "instructions"),
    "contraindications": ("contraindication", "must not", "do not take", "allergy"),
    "warnings": ("warning", "warnings", "precaution", "caution"),
    "side_effects": ("side effect", "adverse", "effects"),
    "storage": ("storage", "store"),
}

SECTION_PATTERNS: dict[str, tuple[str, ...]] = {
    "indications": ("indication", "what is", "used for", "therapeutic indications"),
    "dosage": ("dose", "dosage", "how to take", "posology", "administration"),
    "contraindications": ("contraindication", "must not", "do not take", "allergy"),
    "warnings": ("warning", "precaution", "special warnings", "caution"),
    "side_effects": ("side effect", "adverse", "undesirable effects"),
    "storage": ("storage", "store", "shelf life", "expiry"),
}

SOURCE_PRIORITY: dict[str, int] = {
    "products.mhra.gov.uk": 100,
    "www.medicines.org.uk": 90,
    "medicines.org.uk": 90,
    "www.ema.europa.eu": 80,
    "www.accessdata.fda.gov": 75,
    "dailymed.nlm.nih.gov": 70,
    "www.gov.uk": 60,
    "www.who.int": 50,
    "who.int": 50,
}


def _normalize(value: str) -> str:
    return " ".join(str(value).lower().split())


def _allowed_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    host = (parsed.netloc or "").lower()
    return parsed.scheme == "https" and host in {domain.lower() for domain in settings.allowed_external_domains}


def _validate_reference_urls(urls: list[str]) -> tuple[list[str], list[str], list[str]]:
    valid_urls: list[str] = []
    invalid_urls: list[str] = []
    blocked_urls: list[str] = []
    for raw_url in urls:
        url = str(raw_url).strip()
        try:
            parsed = urlparse(url)
        except ValueError:
            invalid_urls.append(url)
            continue
        if parsed.scheme != "https" or not parsed.netloc:
            invalid_urls.append(url)
            continue
        if not _allowed_url(url):
            blocked_urls.append(url)
            continue
        valid_urls.append(url)
    return valid_urls, invalid_urls, blocked_urls


def _cache_path_for_ingredient(active_ingredient: str) -> Path:
    slug = _normalize(active_ingredient).replace(" ", "_")
    return CACHE_DIR / f"innovator_patient_info_{slug}.json"


def _fetch_text(url: str, timeout_seconds: float = 8.0) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": "RegulatoryMCP/1.0 (+synthetic-regulatory-review)",
            "Accept": "text/html,application/pdf,text/plain,*/*",
        },
    )
    with urlopen(request, timeout=timeout_seconds) as response:  # nosec B310 - allowlisted domains only
        raw = response.read()
    text = raw.decode("utf-8", errors="ignore")
    return text


def _html_to_text(html: str) -> str:
    no_script = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    no_tags = re.sub(r"(?is)<[^>]+>", " ", no_script)
    unescaped = (
        no_tags.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
    )
    return re.sub(r"\s+", " ", unescaped).strip()


def _extract_links(html: str, base_url: str) -> list[str]:
    links: list[str] = []
    for match in re.finditer(r"""href\s*=\s*["']([^"']+)["']""", html, flags=re.IGNORECASE):
        href = str(match.group(1)).strip()
        if not href or href.startswith("#"):
            continue
        absolute = urljoin(base_url, href)
        links.append(absolute)
    return links


def _extract_sections_from_text(text: str, source_url: str) -> list[dict[str, Any]]:
    lowered = text.lower()
    sections: list[dict[str, Any]] = []
    for section_name, patterns in SECTION_PATTERNS.items():
        for pattern in patterns:
            idx = lowered.find(pattern)
            if idx >= 0:
                snippet = text[max(idx - 120, 0) : min(idx + 700, len(text))]
                sections.append(
                    PatientInfoSection(
                        section_name=section_name,
                        text=snippet.strip(),
                        source_url=source_url,
                        metadata={"extraction_pattern": pattern},
                    ).model_dump(mode="json")
                )
                break
    return sections


def _source_url_candidates(active_ingredient: str, provided_urls: list[str]) -> list[str]:
    ingredient_q = quote_plus(active_ingredient.strip())
    ingredient_slug = re.sub(r"[^a-z0-9]+", "-", active_ingredient.strip().lower()).strip("-")
    generated = [
        f"https://products.mhra.gov.uk/search/?query={ingredient_q}",
        f"https://products.mhra.gov.uk/?q={ingredient_q}",
        f"https://www.medicines.org.uk/emc/search?q={ingredient_q}",
        f"https://dailymed.nlm.nih.gov/dailymed/search.cfm?query={ingredient_q}",
        f"https://www.ema.europa.eu/en/search?search_api_fulltext={ingredient_q}",
        f"https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?event=BasicSearch.process&searchterm={ingredient_q}",
    ]
    if ingredient_slug:
        generated.append(f"https://products.mhra.gov.uk/search/?query={ingredient_slug}")
    combined: list[str] = []
    seen: set[str] = set()
    for url in [*provided_urls, *generated]:
        normalized = str(url).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        combined.append(normalized)
    return sorted(combined, key=lambda item: -_source_priority(item))


def _source_priority(url: str) -> int:
    host = (urlparse(str(url)).netloc or "").lower()
    return SOURCE_PRIORITY.get(host, 10)


def _compute_section_confidence(section: dict[str, Any], source_url: str) -> float:
    section_text = str(section.get("text", "")).strip()
    base = 0.4
    if len(section_text) > 250:
        base += 0.15
    if len(section_text) > 500:
        base += 0.1
    if section.get("metadata", {}).get("extraction_pattern"):
        base += 0.1
    base += min(_source_priority(source_url) / 1000.0, 0.2)
    return round(min(base, 0.98), 3)


def _is_pil_or_smpc_link(url: str) -> bool:
    lowered = url.lower()
    signals = ("pil", "patient", "leaflet", "smpc", "summary-product-characteristics", "spc")
    return any(signal in lowered for signal in signals)


def _live_fetch_innovator_sections(active_ingredient: str, seed_urls: list[str]) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    warnings: list[str] = []
    visited: set[str] = set()
    harvested_sections: list[dict[str, Any]] = []
    source_refs: list[str] = []
    crawl_queue = _source_url_candidates(active_ingredient, seed_urls)

    while crawl_queue and len(visited) < 30 and len(harvested_sections) < 8:
        current = crawl_queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        if not _allowed_url(current):
            warnings.append(f"Skipped non-allowlisted URL: {current}")
            continue
        try:
            payload = _fetch_text(current)
        except Exception as exc:
            warnings.append(f"Could not fetch {current}: {exc.__class__.__name__}")
            continue
        text = _html_to_text(payload)
        sections = _extract_sections_from_text(text, current)
        if sections:
            harvested_sections.extend(sections)
            source_refs.append(current)
        for link in _extract_links(payload, current):
            if link in visited or not _allowed_url(link):
                continue
            if _is_pil_or_smpc_link(link):
                crawl_queue.append(link)

    # Deduplicate by section name, preferring higher-priority source URLs.
    deduped: dict[str, dict[str, Any]] = {}
    for row in harvested_sections:
        key = str(row.get("section_name", "")).lower()
        source_url = str(row.get("source_url", "")).strip()
        if key and key not in deduped:
            deduped[key] = row
        elif key:
            existing_url = str(deduped[key].get("source_url", "")).strip()
            if _source_priority(source_url) > _source_priority(existing_url):
                deduped[key] = row
    return list(deduped.values()), source_refs, warnings


@mcp.tool(name="fetch_innovator_patient_information", description="Fetch cached innovator patient-information sections and validate the supplied reference URLs against the allowed domain list.")
@tool_audit(tool_name="fetch_innovator_patient_information", logger=LOGGER)
def fetch_innovator_patient_information(
    active_ingredient: str,
    reference_urls: list[str] | None = None,
) -> dict[str, Any]:
    """
    Fetch and validate innovator Patient Information Leaflet (PIL) sections.
    
    Args:
        active_ingredient: The INN/Active ingredient name (e.g., 'paracetamol', 'amoxicillin').
        reference_urls: Optional list of external URLs (e.g., https://www.medicines.org.uk/...) to validate.
        
    Example:
        active_ingredient: "paracetamol"
    """
    payload = {
        "active_ingredient": active_ingredient,
        "reference_urls": reference_urls or [],
    }
    request = FetchInnovatorPatientInformationRequest.model_validate(payload)
    cache_path = _cache_path_for_ingredient(request.active_ingredient)
    warnings: list[str] = []
    valid_urls, invalid_urls, blocked_urls = _validate_reference_urls(request.reference_urls)

    if invalid_urls:
        raise ValueError(f"Invalid reference URL(s): {', '.join(invalid_urls)}")
    if request.reference_urls and not valid_urls and blocked_urls:
        raise ValueError(f"Blocked reference URL domain(s): {', '.join(blocked_urls)}")
    if blocked_urls:
        warnings.append("Some supplied reference URLs were rejected because they are outside the allowed domain list.")
    cached: dict[str, Any] | None = None
    if cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))

    sections: list[dict[str, Any]] = []
    raw_source_refs: list[str] = []
    source_type = "cache"
    live_attempted = True
    live_sections, live_refs, live_warnings = _live_fetch_innovator_sections(
        request.active_ingredient,
        valid_urls,
    )
    warnings.extend(live_warnings)
    if live_sections:
        sections = live_sections
        raw_source_refs = live_refs
        source_type = "external"

    if not sections and cached:
        sections = [
            PatientInfoSection(
                section_name=row["section_name"],
                text=row["text"],
                source_url=(cached.get("raw_source_refs") or valid_urls or [None])[0],
            ).model_dump(mode="json")
            for row in cached.get("sections", [])
        ]
        raw_source_refs = list(cached.get("raw_source_refs", []))
        source_type = "cache"

    if not sections:
        raise ValueError(
            f"No innovator patient-information could be retrieved for {request.active_ingredient} from supplied or fallback sources."
        )

    section_provenance: list[dict[str, Any]] = []
    for section in sections:
        source_url = str(section.get("source_url") or (raw_source_refs[0] if raw_source_refs else "")).strip()
        source_domain = (urlparse(source_url).netloc or "").lower() if source_url else None
        confidence = _compute_section_confidence(section, source_url) if source_url else 0.6
        if source_url:
            section.setdefault("metadata", {})
            section["metadata"]["source_domain"] = source_domain
            section["metadata"]["source_priority"] = _source_priority(source_url)
            section["metadata"]["confidence_score"] = confidence
        section_provenance.append(
            {
                "section_name": section.get("section_name"),
                "source_url": source_url or None,
                "source_domain": source_domain,
                "source_priority": _source_priority(source_url) if source_url else None,
                "confidence_score": confidence,
            }
        )

    return build_tool_envelope(
        tool_name="fetch_innovator_patient_information",
        payload=payload,
        data={
            "reference_product": (cached or {}).get("reference_product", f"{request.active_ingredient} reference"),
            "sections": sections,
            "raw_source_refs": raw_source_refs,
            "source_selection_policy": {
                "order": ["products.mhra.gov.uk", "medicines.org.uk", "ema.europa.eu", "accessdata.fda.gov", "dailymed.nlm.nih.gov", "gov.uk", "who.int"],
                "strategy": "prefer_highest_priority_source_per_section",
            },
            "section_provenance": section_provenance,
        },
        warnings=warnings,
        source_refs=[
            {
                "source": "innovator_patient_information",
                "source_type": source_type,
                "metadata": {
                    "path": str(cache_path),
                    "active_ingredient": request.active_ingredient,
                    "live_attempted": live_attempted,
                    "validated_reference_urls": valid_urls,
                    "blocked_reference_urls": blocked_urls,
                },
            }
        ],
    )


@mcp.tool(name="compare_generic_patient_information", description="Compare current generic patient-information sections against cached innovator reference sections.")
@tool_audit(tool_name="compare_generic_patient_information", logger=LOGGER)
def compare_generic_patient_information(
    current_pil_sections: list[dict[str, Any]],
    innovator_pil_sections: list[dict[str, Any]],
    comparison_dimensions: list[str] | None = None,
) -> dict[str, Any]:
    payload = {
        "current_pil_sections": current_pil_sections,
        "innovator_pil_sections": innovator_pil_sections,
        "comparison_dimensions": comparison_dimensions,
    }
    request = CompareGenericPatientInformationRequest.model_validate(payload)
    dimensions = request.comparison_dimensions or [
        "indications",
        "dosage",
        "contraindications",
        "warnings",
        "side_effects",
        "storage",
    ]
    current_text = " ".join(section.text for section in request.current_pil_sections)
    reference_by_section = {section.section_name.lower(): section for section in request.innovator_pil_sections}

    differences: list[dict[str, Any]] = []
    missing_count = 0

    for dimension in dimensions:
        normalized_dimension = dimension.lower()
        ref_section = reference_by_section.get(normalized_dimension)
        if not ref_section:
            continue
        keywords = DIMENSION_KEYWORDS.get(normalized_dimension, (normalized_dimension,))
        lowered_current = current_text.lower()
        keyword_present = any(keyword in lowered_current for keyword in keywords)
        ref_terms = {token for token in re.findall(r"[a-zA-Z]+", ref_section.text.lower()) if len(token) > 4}
        current_terms = {token for token in re.findall(r"[a-zA-Z]+", current_text.lower()) if len(token) > 4}
        overlap = len(ref_terms & current_terms) / max(len(ref_terms), 1)
        if (not keyword_present) or overlap < 0.18:
            missing_count += 1
            severity = "critical" if normalized_dimension in {"contraindications", "warnings"} else "major"
            differences.append(
                {
                    "section": dimension,
                    "issue": f"Current patient information does not align closely with the innovator reference for {dimension}.",
                    "severity": severity,
                    "recommendation": f"Align the generic leaflet wording for {dimension} more closely with the innovator reference or justify the difference.",
                    "current_excerpt": current_text[:220],
                    "reference_excerpt": ref_section.text[:220],
                }
            )

    if missing_count == 0:
        overall_alignment = "aligned"
    elif missing_count <= 2:
        overall_alignment = "partial"
    else:
        overall_alignment = "not_aligned"

    return build_tool_envelope(
        tool_name="compare_generic_patient_information",
        payload=payload,
        data={
            "overall_alignment": overall_alignment,
            "differences": differences,
        },
        warnings=[],
        source_refs=[],
    )
