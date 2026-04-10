from __future__ import annotations

import json
import math
import uuid
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import Settings
from .retrieval import tokenize

try:  # pragma: no cover - optional dependency path
    from langgraph.graph import END, START, StateGraph

    LANGGRAPH_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised via fallback engine
    END = "__end__"
    START = "__start__"
    StateGraph = None
    LANGGRAPH_AVAILABLE = False


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def estimate_tokens(text: str) -> int:
    normalized = " ".join(str(text or "").split())
    if not normalized:
        return 0
    lexical_tokens = len(tokenize(normalized))
    char_tokens = math.ceil(len(normalized) / 4)
    return max(1, lexical_tokens, char_tokens)


def _trim_words(text: str, max_words: int) -> str:
    words = str(text or "").split()
    if len(words) <= max_words:
        return " ".join(words)
    return " ".join(words[:max_words]) + " ..."


def _message_snippet(message: dict[str, Any], max_words: int = 24) -> str:
    role = str(message.get("role", "user")).capitalize()
    content = _trim_words(str(message.get("content", "")), max_words=max_words)
    citations = message.get("citations") or []
    citation_ids = ", ".join(c["citation_id"] for c in citations[:3] if c.get("citation_id"))
    if citation_ids:
        return f"{role}: {content} Evidence: {citation_ids}."
    return f"{role}: {content}"


def _compact_text(text: str, max_tokens: int) -> str:
    if estimate_tokens(text) <= max_tokens:
        return text
    target_words = max(40, int(max_tokens * 0.7))
    return _trim_words(text, max_words=target_words)


def _build_summary_text(
    existing_summary: str,
    carryover_summary: str,
    messages: list[dict[str, Any]],
    dossier_id: str | None,
    max_tokens: int,
) -> str:
    parts: list[str] = []
    if carryover_summary:
        parts.append(f"Carryover context: {carryover_summary}")
    if existing_summary:
        parts.append(f"Prior summary: {existing_summary}")
    if dossier_id:
        parts.append(f"Current dossier focus: {dossier_id}.")
    for message in messages:
        parts.append(_message_snippet(message))
    return _compact_text(" ".join(parts), max_tokens=max_tokens)


def _active_messages(session: dict[str, Any]) -> list[dict[str, Any]]:
    return [message for message in session.get("messages", []) if not message.get("archived", False)]


def _ensure_message_defaults(message: dict[str, Any]) -> dict[str, Any]:
    hydrated = {
        "message_id": str(message.get("message_id", f"msg-{uuid.uuid4().hex[:10]}")),
        "role": str(message.get("role", "user")),
        "content": str(message.get("content", "")),
        "created_at_utc": str(message.get("created_at_utc", _utc_now_iso())),
        "tokens_estimate": int(message.get("tokens_estimate", estimate_tokens(message.get("content", "")))),
        "citations": list(message.get("citations", [])),
        "archived": bool(message.get("archived", False)),
        "metadata": dict(message.get("metadata", {})),
    }
    return hydrated


def _build_context_monitor(session: dict[str, Any], settings: Settings) -> dict[str, Any]:
    carryover_tokens = estimate_tokens(session.get("carryover_summary", ""))
    summary_tokens = estimate_tokens(session.get("rolling_summary", ""))
    active_message_tokens = sum(int(message.get("tokens_estimate", 0)) for message in _active_messages(session))
    context_window_tokens = int(session.get("context_window_tokens", settings.default_context_window_tokens))
    used_tokens = carryover_tokens + summary_tokens + active_message_tokens
    threshold_tokens = max(1, math.floor(context_window_tokens * settings.context_compaction_threshold))
    usage_ratio = round(used_tokens / max(context_window_tokens, 1), 5)
    return {
        "context_window_tokens": context_window_tokens,
        "used_tokens": used_tokens,
        "remaining_tokens": max(context_window_tokens - used_tokens, 0),
        "usage_ratio": usage_ratio,
        "threshold_tokens": threshold_tokens,
        "compaction_threshold_ratio": settings.context_compaction_threshold,
        "rolling_summary_tokens": summary_tokens,
        "carryover_tokens": carryover_tokens,
        "active_message_tokens": active_message_tokens,
        "archived_messages_count": sum(1 for message in session.get("messages", []) if message.get("archived", False)),
        "compaction_count": int(session.get("compaction_count", 0)),
        "auto_compaction_required": used_tokens >= threshold_tokens,
        "last_compacted_at": session.get("last_compacted_at"),
        "conversation_engine": "langgraph" if LANGGRAPH_AVAILABLE else "langgraph_compatible_fallback",
    }


def build_context_monitor(session: dict[str, Any], settings: Settings) -> dict[str, Any]:
    return _build_context_monitor(session, settings)


def build_model_context(session: dict[str, Any], settings: Settings) -> str:
    parts: list[str] = []
    if session.get("carryover_summary"):
        parts.append(f"Linked conversation carryover: {session['carryover_summary']}")
    if session.get("rolling_summary"):
        parts.append(f"Rolling conversation summary: {session['rolling_summary']}")
    active_messages = _active_messages(session)
    if active_messages:
        recent = active_messages[-settings.context_keep_last_messages :]
        parts.append("Recent turns:")
        for message in recent:
            parts.append(_message_snippet(message, max_words=18))
    return "\n".join(parts).strip()


def _compact_session_payload(session: dict[str, Any], settings: Settings, reason: str) -> dict[str, Any]:
    active_messages = _active_messages(session)
    max_summary_tokens = min(512, max(160, int(session["context_window_tokens"] * 0.22)))
    archived_any = False

    def archive_messages(messages_to_archive: list[dict[str, Any]]) -> None:
        nonlocal archived_any
        if not messages_to_archive:
            return
        session["rolling_summary"] = _build_summary_text(
            existing_summary=str(session.get("rolling_summary", "")),
            carryover_summary="",
            messages=messages_to_archive,
            dossier_id=session.get("dossier_id"),
            max_tokens=max_summary_tokens,
        )
        archive_ids = {message["message_id"] for message in messages_to_archive}
        for message in session.get("messages", []):
            if message["message_id"] in archive_ids:
                message["archived"] = True
        session["compaction_count"] = int(session.get("compaction_count", 0)) + 1
        session["last_compacted_at"] = _utc_now_iso()
        session["last_compaction_reason"] = reason
        session["summary_model_id"] = session.get("summary_model_id") or settings.low_cost_summary_model_id
        session.setdefault("summary_history", []).append(
            {
                "created_at_utc": session["last_compacted_at"],
                "summary_model_id": session["summary_model_id"],
                "summary_text": session["rolling_summary"],
                "source_message_count": len(messages_to_archive),
                "reason": reason,
                "tokens_estimate": estimate_tokens(session["rolling_summary"]),
            }
        )
        archived_any = True

    keep_count = min(max(1, settings.context_keep_last_messages), len(active_messages))
    if len(active_messages) <= keep_count:
        keep_count = 1 if len(active_messages) > 1 else 0
    archive_messages(active_messages[:-keep_count] if keep_count > 0 else active_messages)

    while _build_context_monitor(session, settings)["auto_compaction_required"]:
        active_messages = _active_messages(session)
        if not active_messages:
            break
        if len(active_messages) == 1:
            last_message = active_messages[0]
            trimmed = _trim_words(last_message["content"], max_words=max(32, int(max_summary_tokens * 0.45)))
            if trimmed == last_message["content"]:
                break
            session["rolling_summary"] = _build_summary_text(
                existing_summary=str(session.get("rolling_summary", "")),
                carryover_summary="",
                messages=[last_message],
                dossier_id=session.get("dossier_id"),
                max_tokens=max_summary_tokens,
            )
            last_message["content"] = trimmed
            last_message["tokens_estimate"] = estimate_tokens(trimmed)
            session["compaction_count"] = int(session.get("compaction_count", 0)) + 1
            session["last_compacted_at"] = _utc_now_iso()
            session["last_compaction_reason"] = f"{reason}_trimmed_last_message"
            archived_any = True
            break
        archive_messages([active_messages[0]])

    if not archived_any:
        session["last_compaction_reason"] = reason
    return session


def _ensure_session_defaults(session: dict[str, Any], settings: Settings) -> dict[str, Any]:
    hydrated = {
        "conversation_id": str(session.get("conversation_id", f"conv-{uuid.uuid4().hex[:10]}")),
        "title": str(session.get("title", "Untitled review thread")),
        "created_at_utc": str(session.get("created_at_utc", _utc_now_iso())),
        "updated_at_utc": str(session.get("updated_at_utc", _utc_now_iso())),
        "linked_from_conversation_id": session.get("linked_from_conversation_id"),
        "context_window_tokens": int(session.get("context_window_tokens", settings.default_context_window_tokens)),
        "selected_model_id": str(session.get("selected_model_id", settings.model_id)),
        "summary_model_id": str(session.get("summary_model_id", settings.low_cost_summary_model_id)),
        "dossier_id": session.get("dossier_id"),
        "carryover_summary": str(session.get("carryover_summary", "")),
        "rolling_summary": str(session.get("rolling_summary", "")),
        "compaction_count": int(session.get("compaction_count", 0)),
        "last_compacted_at": session.get("last_compacted_at"),
        "last_compaction_reason": session.get("last_compaction_reason"),
        "summary_history": list(session.get("summary_history", [])),
        "messages": [_ensure_message_defaults(message) for message in session.get("messages", [])],
    }
    hydrated["context_window_tokens"] = max(
        settings.min_context_window_tokens,
        min(hydrated["context_window_tokens"], settings.max_context_window_tokens),
    )
    return hydrated


@dataclass
class _FallbackConversationGraph:
    settings: Settings

    def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
        session = state["session"]
        monitor = _build_context_monitor(session, self.settings)
        if monitor["auto_compaction_required"]:
            session = _compact_session_payload(
                session=session,
                settings=self.settings,
                reason=str(state.get("reason", "threshold")),
            )
            monitor = _build_context_monitor(session, self.settings)
            state["compacted"] = True
        else:
            state["compacted"] = False
        state["session"] = session
        state["monitor"] = monitor
        return state


def _build_conversation_graph(settings: Settings) -> Any:
    fallback = _FallbackConversationGraph(settings)
    if not LANGGRAPH_AVAILABLE:
        return fallback

    def hydrate_context(state: dict[str, Any]) -> dict[str, Any]:
        state["monitor"] = _build_context_monitor(state["session"], settings)
        state["compacted"] = False
        return state

    def compact_context(state: dict[str, Any]) -> dict[str, Any]:
        monitor = state["monitor"]
        if monitor["auto_compaction_required"]:
            state["session"] = _compact_session_payload(
                session=state["session"],
                settings=settings,
                reason=str(state.get("reason", "threshold")),
            )
            state["monitor"] = _build_context_monitor(state["session"], settings)
            state["compacted"] = True
        return state

    builder = StateGraph(dict)
    builder.add_node("hydrate_context", hydrate_context)
    builder.add_node("compact_context", compact_context)
    builder.add_edge(START, "hydrate_context")
    builder.add_edge("hydrate_context", "compact_context")
    builder.add_edge("compact_context", END)
    return builder.compile()


class ConversationStore:
    def __init__(self, path: Path, settings: Settings) -> None:
        self.path = path
        self.settings = settings
        self.graph = _build_conversation_graph(settings)

    def _load_sessions(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        sessions = payload.get("sessions", payload if isinstance(payload, list) else [])
        return [_ensure_session_defaults(session, self.settings) for session in sessions]

    def _write_sessions(self, sessions: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"sessions": sessions}, ensure_ascii=True, indent=2), encoding="utf-8")

    def list_sessions(self) -> list[dict[str, Any]]:
        sessions = self._load_sessions()
        sessions.sort(key=lambda session: session.get("updated_at_utc", ""), reverse=True)
        return sessions

    def get_session(self, conversation_id: str) -> dict[str, Any] | None:
        for session in self._load_sessions():
            if session["conversation_id"] == conversation_id:
                return session
        return None

    def _run_graph(self, session: dict[str, Any], reason: str) -> tuple[dict[str, Any], dict[str, Any], bool]:
        result = self.graph.invoke({"session": session, "reason": reason})
        return result["session"], result["monitor"], bool(result.get("compacted", False))

    def create_session(
        self,
        title: str | None = None,
        context_window_tokens: int | None = None,
        linked_from_conversation_id: str | None = None,
        selected_model_id: str | None = None,
        dossier_id: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        sessions = self._load_sessions()
        linked_session: dict[str, Any] | None = None
        if linked_from_conversation_id:
            for existing in sessions:
                if existing["conversation_id"] == linked_from_conversation_id:
                    linked_session = existing
                    break
            if linked_session is None:
                raise KeyError(f"Conversation {linked_from_conversation_id} not found")

        now = _utc_now_iso()
        context_window = context_window_tokens or self.settings.default_context_window_tokens
        context_window = max(self.settings.min_context_window_tokens, min(context_window, self.settings.max_context_window_tokens))

        carryover_summary = ""
        if linked_session is not None:
            linked_session, _, _ = self._run_graph(deepcopy(linked_session), reason="link_carryover")
            carryover_summary = _build_summary_text(
                existing_summary=str(linked_session.get("rolling_summary", "")),
                carryover_summary=str(linked_session.get("carryover_summary", "")),
                messages=_active_messages(linked_session),
                dossier_id=linked_session.get("dossier_id"),
                max_tokens=min(320, max(120, int(context_window * 0.18))),
            )
            for idx, existing in enumerate(sessions):
                if existing["conversation_id"] == linked_session["conversation_id"]:
                    sessions[idx] = linked_session
                    break

        session = _ensure_session_defaults(
            {
                "conversation_id": f"conv-{uuid.uuid4().hex[:10]}",
                "title": title or f"Review thread {len(sessions) + 1}",
                "created_at_utc": now,
                "updated_at_utc": now,
                "linked_from_conversation_id": linked_from_conversation_id,
                "context_window_tokens": context_window,
                "selected_model_id": selected_model_id or self.settings.model_id,
                "summary_model_id": self.settings.low_cost_summary_model_id,
                "dossier_id": dossier_id,
                "carryover_summary": carryover_summary,
                "rolling_summary": "",
                "messages": [],
            },
            self.settings,
        )
        session, monitor, _ = self._run_graph(session, reason="session_created")
        sessions.append(session)
        self._write_sessions(sessions)
        return session, monitor

    def update_context_window(self, conversation_id: str, context_window_tokens: int) -> tuple[dict[str, Any], dict[str, Any], bool]:
        sessions = self._load_sessions()
        updated_session: dict[str, Any] | None = None
        monitor: dict[str, Any] | None = None
        compacted = False
        normalized_window = max(
            self.settings.min_context_window_tokens,
            min(context_window_tokens, self.settings.max_context_window_tokens),
        )
        for idx, session in enumerate(sessions):
            if session["conversation_id"] != conversation_id:
                continue
            session["context_window_tokens"] = normalized_window
            session["updated_at_utc"] = _utc_now_iso()
            updated_session, monitor, compacted = self._run_graph(session, reason="context_window_updated")
            sessions[idx] = updated_session
            break
        if updated_session is None or monitor is None:
            raise KeyError(f"Conversation {conversation_id} not found")
        self._write_sessions(sessions)
        return updated_session, monitor, compacted

    def append_turn(
        self,
        conversation_id: str,
        user_content: str,
        assistant_content: str,
        selected_model_id: str,
        citations: list[dict[str, Any]] | None = None,
        dossier_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any], bool]:
        sessions = self._load_sessions()
        updated_session: dict[str, Any] | None = None
        monitor: dict[str, Any] | None = None
        compacted = False
        for idx, session in enumerate(sessions):
            if session["conversation_id"] != conversation_id:
                continue
            now = _utc_now_iso()
            session["updated_at_utc"] = now
            session["selected_model_id"] = selected_model_id
            if dossier_id:
                session["dossier_id"] = dossier_id
            session["messages"].extend(
                [
                    _ensure_message_defaults(
                        {
                            "message_id": f"msg-{uuid.uuid4().hex[:10]}",
                            "role": "user",
                            "content": user_content,
                            "created_at_utc": now,
                            "tokens_estimate": estimate_tokens(user_content),
                            "metadata": metadata or {},
                        }
                    ),
                    _ensure_message_defaults(
                        {
                            "message_id": f"msg-{uuid.uuid4().hex[:10]}",
                            "role": "assistant",
                            "content": assistant_content,
                            "created_at_utc": now,
                            "tokens_estimate": estimate_tokens(assistant_content),
                            "citations": citations or [],
                            "metadata": metadata or {},
                        }
                    ),
                ]
            )
            updated_session, monitor, compacted = self._run_graph(session, reason="conversation_turn_appended")
            sessions[idx] = updated_session
            break
        if updated_session is None or monitor is None:
            raise KeyError(f"Conversation {conversation_id} not found")
        self._write_sessions(sessions)
        return updated_session, monitor, compacted
