from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from regulatory_mcp_server.schemas import ToolAuditRecord, ToolEnvelope


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_input_hash(payload: dict[str, Any]) -> str:
    normalized = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def append_audit_record(path: Path, record: dict[str, Any]) -> None:
    ensure_parent_dir(path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def build_tool_envelope(
    *,
    tool_name: str,
    payload: dict[str, Any],
    data: dict[str, Any],
    warnings: list[str] | None = None,
    source_refs: list[dict[str, Any]] | None = None,
    status: str = "success",
    request_id: str | None = None,
) -> dict[str, Any]:
    rid = request_id or f"{tool_name}-{uuid4().hex[:12]}"
    envelope = ToolEnvelope(
        status=status,
        data=data,
        warnings=warnings or [],
        source_refs=source_refs or [],
        audit=ToolAuditRecord(
            tool_name=tool_name,
            timestamp=utc_timestamp(),
            request_id=rid,
            input_hash=stable_input_hash(payload),
        ),
    )
    return envelope.model_dump(mode="json")


def build_error_envelope(
    *,
    tool_name: str,
    payload: dict[str, Any],
    message: str,
    warnings: list[str] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    return build_tool_envelope(
        tool_name=tool_name,
        payload=payload,
        data={"error": message},
        warnings=warnings or [],
        source_refs=[],
        status="error",
        request_id=request_id,
    )


import functools

def tool_audit(
    tool_name: str,
    logger: logging.Logger,
) -> Callable[[Callable[..., dict[str, Any]]], Callable[..., dict[str, Any]]]:
    def decorator(func: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
            from regulatory_mcp_server.app import settings
            request_id = f"{tool_name}-{uuid4().hex[:12]}"
            payload = kwargs  # FastMCP tools usually receive kwargs
            logger.info("tool_call_started tool=%s request_id=%s", tool_name, request_id)
            try:
                result = func(*args, **kwargs)
                result.setdefault("audit", {})
                result["audit"].setdefault("tool_name", tool_name)
                result["audit"].setdefault("timestamp", utc_timestamp())
                result["audit"].setdefault("request_id", request_id)
                result["audit"].setdefault("input_hash", stable_input_hash(payload))
                append_audit_record(
                    Path(settings.audit_log_path),
                    {
                        "tool_name": tool_name,
                        "request_id": request_id,
                        "timestamp": result["audit"]["timestamp"],
                        "status": result.get("status", "unknown"),
                        "warnings": result.get("warnings", []),
                        "input_hash": result["audit"]["input_hash"],
                    },
                )
                logger.info("tool_call_finished tool=%s request_id=%s status=%s", tool_name, request_id, result.get("status"))
                return result
            except Exception as exc:
                logger.exception("tool_call_failed tool=%s request_id=%s", tool_name, request_id)
                error_result = build_error_envelope(
                    tool_name=tool_name,
                    payload=payload,
                    message=str(exc),
                    request_id=request_id,
                )
                append_audit_record(
                    Path(settings.audit_log_path),
                    {
                        "tool_name": tool_name,
                        "request_id": request_id,
                        "timestamp": error_result["audit"]["timestamp"],
                        "status": "error",
                        "warnings": error_result.get("warnings", []),
                        "input_hash": error_result["audit"]["input_hash"],
                        "error": str(exc),
                    },
                )
                return error_result
        return wrapper
    return decorator


def audit_tool_call(

    *,
    tool_name: str,
    payload: dict[str, Any],
    audit_log_path: Path,
    logger: logging.Logger,
    executor: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    request_id = f"{tool_name}-{uuid4().hex[:12]}"
    logger.info("tool_call_started tool=%s request_id=%s", tool_name, request_id)
    try:
        result = executor(payload)
        result.setdefault("audit", {})
        result["audit"].setdefault("tool_name", tool_name)
        result["audit"].setdefault("timestamp", utc_timestamp())
        result["audit"].setdefault("request_id", request_id)
        result["audit"].setdefault("input_hash", stable_input_hash(payload))
        append_audit_record(
            audit_log_path,
            {
                "tool_name": tool_name,
                "request_id": request_id,
                "timestamp": result["audit"]["timestamp"],
                "status": result.get("status", "unknown"),
                "warnings": result.get("warnings", []),
                "input_hash": result["audit"]["input_hash"],
            },
        )
        logger.info("tool_call_finished tool=%s request_id=%s status=%s", tool_name, request_id, result.get("status"))
        return result
    except Exception as exc:
        logger.exception("tool_call_failed tool=%s request_id=%s", tool_name, request_id)
        error_result = build_error_envelope(
            tool_name=tool_name,
            payload=payload,
            message=str(exc),
            request_id=request_id,
        )
        append_audit_record(
            audit_log_path,
            {
                "tool_name": tool_name,
                "request_id": request_id,
                "timestamp": error_result["audit"]["timestamp"],
                "status": "error",
                "warnings": error_result.get("warnings", []),
                "input_hash": error_result["audit"]["input_hash"],
                "error": str(exc),
            },
        )
        return error_result
