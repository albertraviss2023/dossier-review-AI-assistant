from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any


def _bytes_to_gb(value: int) -> float:
    return round(value / (1024**3), 4)


@dataclass
class InteractionMetrics:
    start_time: float = field(default_factory=time.perf_counter)
    latency_seconds: float = 0.0
    input_tokens_estimate: int = 0
    output_tokens_estimate: int = 0

    def finalize(self, input_text: str = "", output_text: str = "") -> None:
        self.latency_seconds = round(time.perf_counter() - self.start_time, 4)
        # Simple whitespace heuristic for token estimation if no tokenizer available
        if input_text:
            self.input_tokens_estimate = len(input_text.split()) + len(input_text) // 4
        if output_text:
            self.output_tokens_estimate = len(output_text.split()) + len(output_text) // 4


def memory_snapshot() -> dict[str, Any]:
    try:
        import psutil
    except Exception:
        return {
            "process_rss_gb": 0.0,
            "system_total_ram_gb": 0.0,
            "system_available_ram_gb": 0.0,
            "system_used_ram_percent": 0.0,
            "pid": os.getpid(),
            "source": "unavailable",
        }

    process = psutil.Process(os.getpid())
    vm = psutil.virtual_memory()
    return {
        "process_rss_gb": _bytes_to_gb(process.memory_info().rss),
        "system_total_ram_gb": _bytes_to_gb(vm.total),
        "system_available_ram_gb": _bytes_to_gb(vm.available),
        "system_used_ram_percent": float(vm.percent),
        "pid": os.getpid(),
        "source": "psutil",
    }

