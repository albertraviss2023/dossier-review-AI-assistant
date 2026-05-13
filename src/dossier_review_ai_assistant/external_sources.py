from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

from .config import Settings


def _normalize_name(value: str) -> str:
    return " ".join(value.lower().replace("-", " ").split())


@dataclass(frozen=True)
class SnapshotLookupResult:
    normalized_ingredient: str
    normalization_source: str
    active_moiety: str
    parent_compound: str
    pubchem_cid: str
    canonical_smiles: str
    inchikey: str
    chembl_id: str
    unichem_id: str
    aware_category: str
    glass_resistance_trend: str
    similarity_to_existing_watch: str
    existing_watch_comparator: str
    chemistry_source: str
    source_mode: str
    source_trace: list[str]


@lru_cache(maxsize=4)
def load_snapshot_json(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _fetch_json(url: str, timeout_seconds: float) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": "dossier-review-ai-assistant/0.1"})
    with urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def _render_live_url(template: str, **params: str) -> str:
    rendered = template
    for key, value in params.items():
        rendered = rendered.replace(f"{{{key}}}", quote(value))
    return rendered


def _fallback_result(dossier: dict[str, Any]) -> SnapshotLookupResult:
    product = dossier.get("product", {})
    signals = dossier.get("policy_signals", {})
    inn_name = _normalize_name(str(product.get("inn_name", "")))
    product_name = _normalize_name(str(product.get("product_name", "")))
    normalized_ingredient = inn_name or product_name
    if not normalized_ingredient:
        return SnapshotLookupResult(
            normalized_ingredient="not_available",
            normalization_source="missing_product_identity",
            active_moiety="not_available",
            parent_compound="not_available",
            pubchem_cid="not_available",
            canonical_smiles="not_available",
            inchikey="not_available",
            chembl_id="not_available",
            unichem_id="not_available",
            aware_category=str(signals.get("aware_category", "not_applicable")),
            glass_resistance_trend=str(signals.get("glass_resistance_trend", "not_applicable")),
            similarity_to_existing_watch=str(signals.get("similarity_to_existing_watch", "not_applicable")),
            existing_watch_comparator=str(signals.get("existing_watch_comparator", "not_applicable")),
            chemistry_source="missing_product_identity",
            source_mode="signals_fallback",
            source_trace=["No INN available for source lookup; fell back to dossier policy_signals."],
        )
    return SnapshotLookupResult(
        normalized_ingredient=normalized_ingredient,
        normalization_source="raw_product_fields",
        active_moiety="not_available",
        parent_compound="not_available",
        pubchem_cid="not_available",
        canonical_smiles="not_available",
        inchikey="not_available",
        chembl_id="not_available",
        unichem_id="not_available",
        aware_category=str(signals.get("aware_category", "not_applicable")),
        glass_resistance_trend=str(signals.get("glass_resistance_trend", "not_applicable")),
        similarity_to_existing_watch=str(signals.get("similarity_to_existing_watch", "not_applicable")),
        existing_watch_comparator=str(signals.get("existing_watch_comparator", "not_applicable")),
        chemistry_source="signals_fallback",
        source_mode="signals_fallback",
        source_trace=["Source lookup started from dossier product identity and policy_signals."],
    )


def resolve_snapshot_sources(dossier: dict[str, Any], snapshots_dir: Path) -> SnapshotLookupResult:
    fallback = _fallback_result(dossier)
    normalized_ingredient = fallback.normalized_ingredient
    source_trace: list[str] = []

    if normalized_ingredient == "not_available":
        return fallback

    # Use a dictionary to store snapshot payloads for easier access
    snapshot_filenames = {
        "rxnorm": "rxnorm_snapshot_2026-04-11.json",
        "aware": "who_aware_snapshot_2026-04-11.json",
        "glass": "who_glass_snapshot_2026-04-11.json",
        "chemistry": "chemistry_similarity_snapshot_2026-04-11.json",
    }
    
    payloads = {}
    for key, filename in snapshot_filenames.items():
        path = snapshots_dir / filename
        if path.exists():
            payloads[key] = load_snapshot_json(str(path))
        else:
            payloads[key] = {"records": []}

    rxnorm_payload = payloads["rxnorm"]
    rxnorm_entry = next(
        (
            row
            for row in rxnorm_payload.get("records", [])
            if normalized_ingredient in {_normalize_name(str(alias)) for alias in row.get("aliases", [])}
        ),
        None,
    )
    normalization_source = fallback.normalization_source
    if rxnorm_entry:
        normalized_ingredient = _normalize_name(str(rxnorm_entry.get("normalized_ingredient", normalized_ingredient)))
        normalization_source = f"rxnorm_snapshot:{rxnorm_payload.get('snapshot_version', 'unknown')}"
        source_trace.append(
            f"RxNorm snapshot {rxnorm_payload.get('snapshot_version', 'unknown')} normalized product identity to {normalized_ingredient}."
        )
    else:
        source_trace.append(
            f"RxNorm snapshot had no normalization entry for {normalized_ingredient}; used dossier product identity as provided."
        )

    aware_payload = payloads["aware"]
    aware_entry = next(
        (
            row
            for row in aware_payload.get("records", [])
            if _normalize_name(str(row.get("inn_name", ""))) == normalized_ingredient
        ),
        None,
    )
    glass_payload = payloads["glass"]
    glass_entry = next(
        (
            row
            for row in glass_payload.get("records", [])
            if _normalize_name(str(row.get("inn_name", ""))) == normalized_ingredient
        ),
        None,
    )
    chemistry_payload = payloads["chemistry"]
    chemistry_entry = next(
        (
            row
            for row in chemistry_payload.get("records", [])
            if _normalize_name(str(row.get("normalized_ingredient", ""))) == normalized_ingredient
        ),
        None,
    )

    aware_category = str(aware_entry.get("aware_category", fallback.aware_category)) if aware_entry else fallback.aware_category
    glass_trend = (
        str(glass_entry.get("glass_resistance_trend", fallback.glass_resistance_trend))
        if glass_entry
        else fallback.glass_resistance_trend
    )
    similarity = (
        str(chemistry_entry.get("similarity_to_existing_watch", fallback.similarity_to_existing_watch))
        if chemistry_entry
        else fallback.similarity_to_existing_watch
    )
    comparator = (
        str(chemistry_entry.get("existing_watch_comparator", fallback.existing_watch_comparator))
        if chemistry_entry
        else fallback.existing_watch_comparator
    )
    chemistry_source = (
        f"chemistry_snapshot:{chemistry_payload.get('snapshot_version', 'unknown')}"
        if chemistry_entry
        else fallback.chemistry_source
    )
    active_moiety = str(chemistry_entry.get("active_moiety", fallback.active_moiety)) if chemistry_entry else fallback.active_moiety
    parent_compound = (
        str(chemistry_entry.get("parent_compound", fallback.parent_compound))
        if chemistry_entry
        else fallback.parent_compound
    )
    pubchem_cid = str(chemistry_entry.get("pubchem_cid", fallback.pubchem_cid)) if chemistry_entry else fallback.pubchem_cid
    canonical_smiles = (
        str(chemistry_entry.get("canonical_smiles", fallback.canonical_smiles))
        if chemistry_entry
        else fallback.canonical_smiles
    )
    inchikey = str(chemistry_entry.get("inchikey", fallback.inchikey)) if chemistry_entry else fallback.inchikey
    chembl_id = str(chemistry_entry.get("chembl_id", fallback.chembl_id)) if chemistry_entry else fallback.chembl_id
    unichem_id = str(chemistry_entry.get("unichem_id", fallback.unichem_id)) if chemistry_entry else fallback.unichem_id

    if aware_entry:
        source_trace.append(
            f"WHO AWaRe snapshot {aware_payload.get('snapshot_version', 'unknown')} resolved {normalized_ingredient} as {aware_category}."
        )
    else:
        source_trace.append(f"WHO AWaRe snapshot had no entry for {normalized_ingredient}; fell back to dossier policy_signals.")

    if glass_entry:
        source_trace.append(
            f"WHO GLASS snapshot {glass_payload.get('snapshot_version', 'unknown')} resolved {normalized_ingredient} trend as {glass_trend}."
        )
    else:
        source_trace.append(f"WHO GLASS snapshot had no entry for {normalized_ingredient}; fell back to dossier policy_signals.")

    if chemistry_entry:
        source_trace.append(
            f"Chemistry snapshot {chemistry_payload.get('snapshot_version', 'unknown')} resolved Watch similarity as {similarity} against comparator {comparator}."
        )
        source_trace.append(
            f"Chemistry snapshot provided active moiety {active_moiety}, parent compound {parent_compound}, PubChem CID {pubchem_cid}, ChEMBL {chembl_id}, and UniChem {unichem_id}."
        )
    else:
        source_trace.append(
            f"Chemistry snapshot had no entry for {normalized_ingredient}; fell back to dossier policy_signals for Watch similarity."
        )

    source_mode = "snapshot_backed" if aware_entry or glass_entry or chemistry_entry else fallback.source_mode
    return SnapshotLookupResult(
        normalized_ingredient=normalized_ingredient,
        normalization_source=normalization_source,
        active_moiety=active_moiety,
        parent_compound=parent_compound,
        pubchem_cid=pubchem_cid,
        canonical_smiles=canonical_smiles,
        inchikey=inchikey,
        chembl_id=chembl_id,
        unichem_id=unichem_id,
        aware_category=aware_category,
        glass_resistance_trend=glass_trend,
        similarity_to_existing_watch=similarity,
        existing_watch_comparator=comparator,
        chemistry_source=chemistry_source,
        source_mode=source_mode,
        source_trace=source_trace,
    )


def _resolve_live_sources(
    *,
    base_result: SnapshotLookupResult,
    settings: Settings,
    dossier: dict[str, Any],
) -> SnapshotLookupResult:
    normalized_ingredient = base_result.normalized_ingredient
    source_trace = list(base_result.source_trace)
    aware_category = base_result.aware_category
    glass_trend = base_result.glass_resistance_trend
    similarity = base_result.similarity_to_existing_watch
    comparator = base_result.existing_watch_comparator
    normalization_source = base_result.normalization_source
    active_moiety = base_result.active_moiety
    parent_compound = base_result.parent_compound
    pubchem_cid = base_result.pubchem_cid
    canonical_smiles = base_result.canonical_smiles
    inchikey = base_result.inchikey
    chembl_id = base_result.chembl_id
    unichem_id = base_result.unichem_id
    chemistry_source = base_result.chemistry_source
    live_hits = 0

    if normalized_ingredient == "not_available":
        return base_result

    def fetch_rxnorm():
        if not settings.rxnorm_live_url: return None
        url = _render_live_url(settings.rxnorm_live_url, query=normalized_ingredient, inn_name=normalized_ingredient, ingredient=normalized_ingredient)
        return ("rxnorm", _fetch_json(url, settings.external_source_timeout_seconds))

    def fetch_aware():
        if not settings.who_aware_live_url: return None
        url = _render_live_url(settings.who_aware_live_url, inn_name=normalized_ingredient, ingredient=normalized_ingredient, query=normalized_ingredient)
        return ("aware", _fetch_json(url, settings.external_source_timeout_seconds))

    def fetch_glass():
        if not settings.who_glass_live_url: return None
        url = _render_live_url(settings.who_glass_live_url, inn_name=normalized_ingredient, ingredient=normalized_ingredient, query=normalized_ingredient)
        return ("glass", _fetch_json(url, settings.external_source_timeout_seconds))

    def fetch_chemistry():
        if not settings.chemistry_similarity_live_url: return None
        url = _render_live_url(settings.chemistry_similarity_live_url, inn_name=normalized_ingredient, ingredient=normalized_ingredient, query=normalized_ingredient)
        return ("chemistry", _fetch_json(url, settings.external_source_timeout_seconds))

    tasks = [fetch_rxnorm, fetch_aware, fetch_glass, fetch_chemistry]
    
    with ThreadPoolExecutor(max_workers=4) as executor:
        future_to_task = {executor.submit(task): task for task in tasks}
        for future in as_completed(future_to_task):
            try:
                res = future.result()
                if not res: continue
                key, payload = res
                if key == "rxnorm":
                    candidate = _normalize_name(str(payload.get("normalized_ingredient", "")))
                    if candidate:
                        normalized_ingredient = candidate
                        normalization_source = f"rxnorm_live:{payload.get('source_version', 'live')}"
                        source_trace.append(f"Live RxNorm adapter normalized product identity to {normalized_ingredient}.")
                        live_hits += 1
                elif key == "aware":
                    candidate = str(payload.get("aware_category", "")).strip().lower()
                    if candidate:
                        aware_category = candidate
                        source_trace.append(f"Live WHO AWaRe adapter resolved {normalized_ingredient} as {aware_category}.")
                        live_hits += 1
                elif key == "glass":
                    candidate = str(payload.get("glass_resistance_trend", "")).strip().lower()
                    if candidate:
                        glass_trend = candidate
                        source_trace.append(f"Live WHO GLASS adapter resolved {normalized_ingredient} trend as {glass_trend}.")
                        live_hits += 1
                elif key == "chemistry":
                    candidate_similarity = str(payload.get("similarity_to_existing_watch", "")).strip().lower()
                    if candidate_similarity:
                        similarity = candidate_similarity
                        comparator = str(payload.get("existing_watch_comparator", comparator)).strip().lower() or comparator
                        active_moiety = str(payload.get("active_moiety", active_moiety))
                        parent_compound = str(payload.get("parent_compound", parent_compound))
                        pubchem_cid = str(payload.get("pubchem_cid", pubchem_cid))
                        canonical_smiles = str(payload.get("canonical_smiles", canonical_smiles))
                        inchikey = str(payload.get("inchikey", inchikey))
                        chembl_id = str(payload.get("chembl_id", chembl_id))
                        unichem_id = str(payload.get("unichem_id", unichem_id))
                        chemistry_source = f"chemistry_live:{payload.get('source_version', 'live')}"
                        source_trace.append(f"Live chemistry adapter resolved Watch similarity as {similarity} against comparator {comparator}.")
                        live_hits += 1
            except Exception as exc:
                source_trace.append(f"External adapter failed ({exc.__class__.__name__}): {str(exc)}")

    source_mode = "live_backed" if live_hits else base_result.source_mode
    return SnapshotLookupResult(
        normalized_ingredient=normalized_ingredient,
        normalization_source=normalization_source,
        active_moiety=active_moiety,
        parent_compound=parent_compound,
        pubchem_cid=pubchem_cid,
        canonical_smiles=canonical_smiles,
        inchikey=inchikey,
        chembl_id=chembl_id,
        unichem_id=unichem_id,
        aware_category=aware_category,
        glass_resistance_trend=glass_trend,
        similarity_to_existing_watch=similarity,
        existing_watch_comparator=comparator,
        chemistry_source=chemistry_source,
        source_mode=source_mode,
        source_trace=source_trace,
    )


def resolve_sources(dossier: dict[str, Any], settings: Settings) -> SnapshotLookupResult:
    snapshot_result = resolve_snapshot_sources(dossier, settings.source_snapshots_dir)
    if settings.external_source_mode != "live_prefer":
        return snapshot_result
    return _resolve_live_sources(base_result=snapshot_result, settings=settings, dossier=dossier)
