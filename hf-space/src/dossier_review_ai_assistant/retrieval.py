from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from hashlib import blake2b
from array import array
from typing import Protocol

from .data import EvidenceChunk

TOKEN_PATTERN = re.compile(r"\b[a-z0-9][a-z0-9\-]{1,}\b")
SPLIT_PATTERN = re.compile(r"\b(?:vs\.?|versus|with|and)\b", re.IGNORECASE)

SEMANTIC_EXPANSIONS = {
    "gmp": ("good", "manufacturing", "practice", "inspection", "certificate"),
    "capa": ("corrective", "preventive", "action"),
    "auth": ("authentication", "authorization"),
    "authorization": ("authorisation", "restricted", "restriction"),
    "restricted": ("authorization", "restriction", "stewardship"),
    "ui": ("interface", "screen", "workflow"),
    "amr": ("antimicrobial", "resistance", "stewardship"),
    "aware": ("who", "antibiotic", "stewardship"),
    "glass": ("resistance", "surveillance", "who"),
    "endpoint": ("outcome", "result"),
    "outcomes": ("outcome", "endpoint", "result"),
    "trial": ("clinical", "study"),
    "trials": ("clinical", "study"),
}


class Retriever(Protocol):
    def search(
        self,
        query: str,
        top_k: int = 5,
        dossier_id: str | None = None,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list["RetrievalHit"]:
        ...


def generate_expanded_queries(
    query: str,
    intent: str,
    *,
    expansion_terms: list[str] | tuple[str, ...] | None = None,
    constraints: list[str] | tuple[str, ...] | None = None,
    max_queries: int = 5,
) -> list[str]:
    """Generate expanded retrieval queries from the rewrite plan and intent."""
    queries = [query]
    lowered = query.lower()

    if intent == "comparative_versus":
        queries.append(f"{query} differences and comparison")
        queries.append(f"distinguish between entities in {query}")
    elif intent == "historical_trend":
        queries.append(f"historical trend for {query}")
        queries.append(f"evolution of {query} over time")
    elif intent == "policy_guidance":
        queries.append(f"regulatory policy for {query}")
        queries.append(f"official guidance on {query}")
    else:
        # Generic expansion
        queries.append(f"details about {query}")
        queries.append(f"requirements for {query}")

    if constraints:
        constraint_phrase = " ".join(constraints[:3])
        if constraint_phrase:
            queries.append(f"{query} constrained to {constraint_phrase}")

    if expansion_terms:
        joined = ", ".join(term for term in expansion_terms[:4])
        if joined:
            queries.append(f"{query} with related terms {joined}")
        for term in expansion_terms[:3]:
            queries.append(f"{query} {term}")

    deduped: list[str] = []
    seen: set[str] = set()
    for item in queries:
        cleaned = " ".join(item.split()).strip()
        key = cleaned.lower()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        deduped.append(cleaned)
    return deduped[:max_queries]


def tokenize(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text.lower())


def _normalize_token(token: str) -> str:
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("ing") and len(token) > 5:
        return token[:-3]
    if token.endswith("ed") and len(token) > 4:
        return token[:-2]
    if token.endswith("s") and len(token) > 4:
        return token[:-1]
    return token


def expand_tokens(tokens: list[str]) -> list[str]:
    expanded: list[str] = []
    for token in tokens:
        normalized = _normalize_token(token)
        expanded.append(normalized)
        if "-" in normalized:
            expanded.extend(part for part in normalized.split("-") if len(part) > 1)
        expanded.extend(SEMANTIC_EXPANSIONS.get(normalized, ()))
    return expanded


def _char_ngrams(text: str, n: int = 3) -> list[str]:
    compact = re.sub(r"\s+", " ", text.lower()).strip()
    if len(compact) < n:
        return [compact] if compact else []
    return [compact[idx : idx + n] for idx in range(len(compact) - n + 1)]


def decompose_query(query: str) -> list[str]:
    normalized = " ".join(query.strip().split())
    if not normalized:
        return []

    lowered = normalized.lower()
    candidate = normalized
    if lowered.startswith("compare "):
        candidate = normalized[8:].strip()

    segments = [segment.strip(" ,.;:") for segment in SPLIT_PATTERN.split(candidate) if segment.strip(" ,.;:")]
    subqueries: list[str] = []
    seen: set[str] = set()

    def _add(value: str) -> None:
        cleaned = " ".join(value.split())
        key = cleaned.lower()
        if len(cleaned) < 3 or key in seen:
            return
        seen.add(key)
        subqueries.append(cleaned)

    _add(normalized)
    for segment in segments:
        _add(segment)
    return subqueries


def merge_hits(*hit_lists: list["RetrievalHit"], top_k: int = 5) -> list["RetrievalHit"]:
    best_by_citation: dict[str, RetrievalHit] = {}
    for hit_list in hit_lists:
        for hit in hit_list:
            current = best_by_citation.get(hit.chunk.citation_id)
            if current is None or hit.score > current.score:
                best_by_citation[hit.chunk.citation_id] = hit
    merged = sorted(best_by_citation.values(), key=lambda item: item.score, reverse=True)
    return merged[:top_k]


@dataclass(frozen=True)
class RetrievalHit:
    chunk: EvidenceChunk
    score: float


class LexicalRetriever:
    def __init__(self, chunks: list[EvidenceChunk]) -> None:
        self.chunks = chunks
        self._tokenized_docs = [tokenize(chunk.text) for chunk in chunks]
        self._doc_lens = [len(tokens) for tokens in self._tokenized_docs]
        self._avg_doc_len = (sum(self._doc_lens) / len(self._doc_lens)) if self._doc_lens else 1.0
        self._doc_freq = self._build_doc_freq(self._tokenized_docs)

    @staticmethod
    def _build_doc_freq(tokenized_docs: list[list[str]]) -> Counter[str]:
        freq: Counter[str] = Counter()
        for doc_tokens in tokenized_docs:
            for token in set(doc_tokens):
                freq[token] += 1
        return freq

    def _idf(self, term: str) -> float:
        total_docs = max(len(self._tokenized_docs), 1)
        doc_freq = self._doc_freq.get(term, 0)
        return math.log((total_docs - doc_freq + 0.5) / (doc_freq + 0.5) + 1.0)

    def _score_doc(self, query_tokens: list[str], doc_tokens: list[str]) -> float:
        if not query_tokens or not doc_tokens:
            return 0.0

        k1 = 1.2
        b = 0.75
        score = 0.0
        tf = Counter(doc_tokens)
        doc_len = len(doc_tokens)

        for term in query_tokens:
            if term not in tf:
                continue
            idf = self._idf(term)
            numerator = tf[term] * (k1 + 1)
            denominator = tf[term] + k1 * (1 - b + b * (doc_len / self._avg_doc_len))
            score += idf * (numerator / denominator)
        return score

    def search(
        self,
        query: str,
        top_k: int = 5,
        dossier_id: str | None = None,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[RetrievalHit]:
        query_tokens = tokenize(query)
        hits: list[RetrievalHit] = []
        for chunk, doc_tokens in zip(self.chunks, self._tokenized_docs, strict=True):
            if dossier_id and chunk.dossier_id != dossier_id:
                continue
            
            # Apply metadata filter
            if metadata_filter:
                match = True
                for key, value in metadata_filter.items():
                    if getattr(chunk, key, None) != value:
                        match = False
                        break
                if not match:
                    continue

            score = self._score_doc(query_tokens, doc_tokens)
            if score > 0:
                hits.append(RetrievalHit(chunk=chunk, score=score))

        hits.sort(key=lambda hit: hit.score, reverse=True)
        return hits[:top_k]


class DenseVectorIndex:
    def __init__(self, dimensions: int = 512) -> None:
        self.dimensions = dimensions
        self.vectors: list[array[float]] = []
        self.norms: list[float] = []

    def _feature_slot(self, feature: str) -> tuple[int, float]:
        digest = blake2b(feature.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, byteorder="little", signed=False)
        index = value % self.dimensions
        sign = -1.0 if ((value >> 8) & 1) else 1.0
        return index, sign

    def encode_counter(self, counter: Counter[str]) -> tuple[array[float], float]:
        vector = array("f", [0.0] * self.dimensions)
        for feature, weight in counter.items():
            index, sign = self._feature_slot(feature)
            vector[index] += float(weight) * sign
        norm = math.sqrt(sum(value * value for value in vector))
        return vector, norm

    def add(self, counter: Counter[str]) -> None:
        vector, norm = self.encode_counter(counter)
        self.vectors.append(vector)
        self.norms.append(norm)

    @staticmethod
    def cosine(query_vector: array[float], query_norm: float, doc_vector: array[float], doc_norm: float) -> float:
        if not query_norm or not doc_norm:
            return 0.0
        dot = sum(left * right for left, right in zip(query_vector, doc_vector, strict=True))
        return dot / (query_norm * doc_norm)


class DenseVectorRetriever:
    def __init__(self, chunks: list[EvidenceChunk], dimensions: int = 512) -> None:
        self.chunks = chunks
        self.index = DenseVectorIndex(dimensions=dimensions)
        self._token_counters = [self._build_token_counter(chunk) for chunk in chunks]
        for counter in self._token_counters:
            self.index.add(counter)

    def _build_token_counter(self, chunk: EvidenceChunk) -> Counter[str]:
        title_tokens = expand_tokens(tokenize(chunk.section_title))
        body_tokens = expand_tokens(tokenize(chunk.text))
        char_tokens = _char_ngrams(f"{chunk.section_title} {chunk.text[:220]}")
        counter: Counter[str] = Counter()
        counter.update(body_tokens)
        counter.update(title_tokens)
        counter.update(title_tokens)
        counter.update(char_tokens)
        return counter

    def _query_counter(self, query: str) -> Counter[str]:
        counter: Counter[str] = Counter()
        expanded = expand_tokens(tokenize(query))
        counter.update(expanded)
        counter.update(_char_ngrams(query))
        return counter

    def search(
        self,
        query: str,
        top_k: int = 5,
        dossier_id: str | None = None,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[RetrievalHit]:
        query_counter = self._query_counter(query)
        query_tokens = {token for token in query_counter if len(token) > 3 and token not in set(_char_ngrams(query))}
        query_vector, query_norm = self.index.encode_counter(query_counter)
        hits: list[RetrievalHit] = []
        for chunk, doc_counter, doc_vector, doc_norm in zip(
            self.chunks,
            self._token_counters,
            self.index.vectors,
            self.index.norms,
            strict=True,
        ):
            if dossier_id and chunk.dossier_id != dossier_id:
                continue
            
            # Apply metadata filter
            if metadata_filter:
                match = True
                for key, value in metadata_filter.items():
                    if getattr(chunk, key, None) != value:
                        match = False
                        break
                if not match:
                    continue

            if query_tokens and not query_tokens.intersection(doc_counter):
                continue
            score = self.index.cosine(query_vector, query_norm, doc_vector, doc_norm)
            if score > 0:
                hits.append(RetrievalHit(chunk=chunk, score=score))
        hits.sort(key=lambda hit: hit.score, reverse=True)
        return hits[:top_k]


class HybridRetriever:
    def __init__(self, chunks: list[EvidenceChunk]) -> None:
        self.chunks = chunks
        self.lexical = LexicalRetriever(chunks)
        self.semantic = DenseVectorRetriever(chunks)

    @staticmethod
    def _rrf_score(rank: int, k: int = 60) -> float:
        return 1.0 / (k + rank)

    def _rerank_score(self, query: str, hit: RetrievalHit, fusion_score: float) -> float:
        query_tokens = set(expand_tokens(tokenize(query)))
        body_tokens = set(expand_tokens(tokenize(hit.chunk.text)))
        title_tokens = set(expand_tokens(tokenize(hit.chunk.section_title)))

        if not query_tokens:
            return fusion_score

        body_overlap = len(query_tokens & body_tokens) / len(query_tokens)
        title_overlap = len(query_tokens & title_tokens) / len(query_tokens)
        short_chunk_bonus = 0.06 if hit.chunk.chunk_token_estimate and hit.chunk.chunk_token_estimate <= 160 else 0.0
        dossier_bonus = 0.04 if hit.chunk.source_type == "dossier_section" else 0.0
        return fusion_score + (0.22 * body_overlap) + (0.16 * title_overlap) + short_chunk_bonus + dossier_bonus

    def search(
        self,
        query: str,
        top_k: int = 5,
        dossier_id: str | None = None,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[RetrievalHit]:
        lexical_hits = self.lexical.search(
            query=query,
            top_k=max(top_k * 3, 10),
            dossier_id=dossier_id,
            metadata_filter=metadata_filter,
        )
        semantic_hits = self.semantic.search(
            query=query,
            top_k=max(top_k * 3, 10),
            dossier_id=dossier_id,
            metadata_filter=metadata_filter,
        )

        fused: dict[str, tuple[EvidenceChunk, float]] = {}
        for rank, hit in enumerate(lexical_hits, start=1):
            score = self._rrf_score(rank)
            current = fused.get(hit.chunk.citation_id, (hit.chunk, 0.0))
            fused[hit.chunk.citation_id] = (hit.chunk, current[1] + score)
        for rank, hit in enumerate(semantic_hits, start=1):
            score = self._rrf_score(rank)
            current = fused.get(hit.chunk.citation_id, (hit.chunk, 0.0))
            fused[hit.chunk.citation_id] = (hit.chunk, current[1] + score)

        reranked = [
            RetrievalHit(chunk=chunk, score=self._rerank_score(query, RetrievalHit(chunk=chunk, score=fusion_score), fusion_score))
            for chunk, fusion_score in fused.values()
        ]
        reranked.sort(key=lambda hit: hit.score, reverse=True)
        return reranked[:top_k]

    def advanced_search(
        self,
        query: str,
        intent: str,
        top_k: int = 5,
        dossier_id: str | None = None,
        expansion_terms: list[str] | tuple[str, ...] | None = None,
        constraints: list[str] | tuple[str, ...] | None = None,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[RetrievalHit]:
        """Perform multi-stage search with expansion and filtering."""
        expanded_queries = generate_expanded_queries(
            query,
            intent,
            expansion_terms=expansion_terms,
            constraints=constraints,
        )
        
        # Determine metadata filter based on intent
        if metadata_filter is None and (intent == "historical_trend" or "approval" in query.lower()):
            metadata_filter = {"category": "regulatory_action"}
        
        all_hits: list[RetrievalHit] = []
        for sub_query in expanded_queries:
            sub_hits = self.search(
                query=sub_query,
                top_k=top_k,
                dossier_id=dossier_id,
                metadata_filter=metadata_filter,
            )
            all_hits.extend(sub_hits)
        
        # De-duplicate and re-sort
        return merge_hits(all_hits, top_k=top_k)
