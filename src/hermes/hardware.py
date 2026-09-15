from __future__ import annotations

import os
import platform

from hermes.domain import HardwareProfile


def discover_hardware() -> HardwareProfile:
    ram_bytes: int | None = None
    if hasattr(os, "sysconf"):
        try:
            ram_bytes = int(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES"))
        except (ValueError, OSError, TypeError):
            ram_bytes = None
    cuda = bool(os.getenv("CUDA_VISIBLE_DEVICES")) and os.getenv("CUDA_VISIBLE_DEVICES") != "-1"
    rocm = bool(os.getenv("ROCR_VISIBLE_DEVICES"))
    return HardwareProfile(
        cpu_count=os.cpu_count() or 1,
        ram_bytes=ram_bytes,
        gpu_present=cuda or rocm,
        gpu_name=os.getenv("HERMES_GPU_NAME"),
        vram_bytes=int(os.environ["HERMES_VRAM_BYTES"]) if os.getenv("HERMES_VRAM_BYTES") else None,
        cuda_available=cuda,
        rocm_available=rocm,
        os=platform.system(),
        architecture=platform.machine(),
    )


def recommend_local_runtime(profile: HardwareProfile) -> dict[str, str]:
    if profile.gpu_present and profile.vram_bytes and profile.vram_bytes >= 24 * 1024**3:
        return {"runtime": "vllm", "quantization": "benchmark-required", "class": "gpu-production"}
    if profile.gpu_present:
        return {"runtime": "sglang-or-vllm", "quantization": "benchmark-required", "class": "gpu"}
    if profile.ram_bytes and profile.ram_bytes >= 16 * 1024**3:
        return {"runtime": "llama.cpp", "quantization": "gguf", "class": "cpu-local"}
    return {"runtime": "remote-required", "quantization": "n/a", "class": "insufficient-local"}
