# core/memory.py
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class MemoryRegion:
    name: str
    num_bytes: int


class MemorySystem:
    """
    Very simple memory model.

    Assumptions:
      - pk, message, signature already exist in memory
      - memory serves 64-bit words
    """

    def __init__(self, config, message_bytes: Optional[int] = None):
        self.config = config
        self.regions: Dict[str, MemoryRegion] = {
            "pk": MemoryRegion("pk", config.PK_BYTES),
            "message": MemoryRegion("message", message_bytes or config.MSG_BYTES),
            "signature": MemoryRegion("signature", config.SIG_BYTES),
        }

    @property
    def beat_bytes(self) -> int:
        return self.config.MEM_BANDWIDTH // 8

    def beats_for_bytes(self, num_bytes: int) -> int:
        return (num_bytes + self.beat_bytes - 1) // self.beat_bytes

    def get_region_bytes(self, name: str) -> int:
        if name not in self.regions:
            raise KeyError(f"Unknown memory region: {name}")
        return self.regions[name].num_bytes

    def set_region_bytes(self, name: str, num_bytes: int) -> None:
        if name not in self.regions:
            self.regions[name] = MemoryRegion(name, num_bytes)
        else:
            self.regions[name].num_bytes = num_bytes

    def summary(self) -> Dict[str, int]:
        return {name: region.num_bytes for name, region in self.regions.items()}


class SlotBuffer:
    """
    Single-slot hardware buffer with payload tagging.
    """

    def __init__(self, name: str):
        self.name = name
        self.payload: Optional[Dict[str, Any]] = None

    @property
    def empty(self) -> bool:
        return self.payload is None

    @property
    def full(self) -> bool:
        return self.payload is not None

    def can_push(self) -> bool:
        return self.empty

    def can_pop(self) -> bool:
        return self.full

    def push(self, payload: Dict[str, Any]) -> None:
        if self.full:
            raise RuntimeError(f"Buffer {self.name} is already full")
        self.payload = payload

    def pop(self) -> Dict[str, Any]:
        if self.empty:
            raise RuntimeError(f"Buffer {self.name} is empty")
        payload = self.payload
        self.payload = None
        return payload

    def peek(self) -> Optional[Dict[str, Any]]:
        return self.payload

    def clear(self) -> None:
        self.payload = None

    def snapshot(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "empty": self.empty,
            "full": self.full,
            "payload": self.payload,
        }

    def __repr__(self) -> str:
        return f"SlotBuffer(name={self.name}, payload={self.payload})"


class BufferPool:
    """
    Central single-slot buffers used by the scheduler.

    Buffers:
      - A_elem    : one generated A[row][col] polynomial
      - z_ntt     : one z polynomial after NTT
      - c_ntt     : challenge polynomial c after NTT
      - t1_ntt    : one t1 row polynomial after NTT
      - w_ntt     : PAU output in NTT domain (partial or full)
      - w_final   : inverse-NTT output polynomial row
      - w1_packed : optional post-processed packed row after use_hint/highbits/pack
    """

    def __init__(self):
        self.buffers = {
            "A_elem": SlotBuffer("A_elem"),
            "z_ntt": SlotBuffer("z_ntt"),
            "c_ntt": SlotBuffer("c_ntt"),
            "t1_ntt": SlotBuffer("t1_ntt"),
            "w_ntt": SlotBuffer("w_ntt"),
            "w_final": SlotBuffer("w_final"),
            "w1_packed": SlotBuffer("w1_packed"),
        }

    def __getitem__(self, key: str) -> SlotBuffer:
        return self.buffers[key]

    def __contains__(self, key: str) -> bool:
        return key in self.buffers

    def keys(self):
        return self.buffers.keys()

    def items(self):
        return self.buffers.items()

    def values(self):
        return self.buffers.values()

    def clear_all(self) -> None:
        for buf in self.buffers.values():
            buf.clear()

    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        return {name: buf.snapshot() for name, buf in self.buffers.items()}