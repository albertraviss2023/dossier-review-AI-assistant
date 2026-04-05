from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from .data import EvidenceChunk

TOKEN_PATTERN = re.compile(r"\b[a-z0-9][a-z0-9\-]{1,}\b")


def tokenize(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text.lower())


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

    def search(self, query: str, top_k: int = 5, dossier_id: str | None = None) -> list[RetrievalHit]:
        query_tokens = tokenize(query)
        hits: list[RetrievalHit] = []
        for chunk, doc_tokens in zip(self.chunks, self._tokenized_docs, strict=True):
            if dossier_id and chunk.dossier_id != dossier_id:
                continue
            score = self._score_doc(query_tokens, doc_tokens)
            if score > 0:
                hits.append(RetrievalHit(chunk=chunk, score=score))

        hits.sort(key=lambda hit: hit.score, reverse=True)
        return hits[:top_k]

