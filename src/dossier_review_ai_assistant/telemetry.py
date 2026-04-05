from __future__ import annotations

import os
from typing import Any


def _bytes_to_gb(value: int) -> float:
    return round(value / (1024**3), 4)


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

