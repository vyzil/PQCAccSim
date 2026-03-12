# modules/hint.py
import math


class HintPackModule:
    """
    Row-wise post-processing after inverse NTT.

    One job corresponds to:
      1) use_hint on one polynomial row
      2) extract w1 (high bits)
      3) pack w1 and store

    This is a timing model only.
    """

    def __init__(self, config):
        self.config = config

        self.state = "IDLE"
        self.cycles_left = 0
        self.cycle_count = 0
        self.done_pulse = False
        self.current_job = None

        self._cycle_getter = None

    @property
    def busy(self) -> bool:
        return self.state != "IDLE"

    # ------------------------------------------------------------------
    # Trace helpers
    # ------------------------------------------------------------------
    def set_cycle_getter(self, fn):
        self._cycle_getter = fn

    def _now(self):
        if self._cycle_getter is None:
            return -1
        return self._cycle_getter()

    def _trace_enabled(self) -> bool:
        return getattr(self.config, "TRACE_ENABLED", False) and getattr(self.config, "TRACE_MODULE_STATES", False)

    def _trace(self, msg: str):
        if not self._trace_enabled():
            return
        print(f"[cycle {self._now():7d}] [HintPackModule  ] {msg}")

    # ------------------------------------------------------------------
    # Timing model
    # ------------------------------------------------------------------
    def estimate_cycles(self) -> int:
        # use_hint + extract highbits
        logic_cycles = math.ceil(self.config.DILITHIUM_N / self.config.USEHINT_PE_COUNT)
        logic_cycles += self.config.USEHINT_PIPELINE_STAGES

        # pack w1 into memory/buffer
        pack_bits = self.config.W1_PACKED_BYTES_PER_POLY * 8
        pack_cycles = math.ceil(pack_bits / self.config.MEM_BANDWIDTH)

        return logic_cycles + pack_cycles

    def start_job(self, row: int, tag=None):
        if self.busy:
            raise RuntimeError("HintPackModule is busy")

        self.current_job = {
            "type": "hint_pack",
            "row": row,
            "tag": tag,
        }
        self.cycles_left = self.estimate_cycles()
        self.cycle_count = 0
        self.done_pulse = False
        self.state = "BUSY"

        self._trace(
            f"IDLE -> BUSY | row={row} cycles={self.cycles_left} tag={tag}"
        )

    def tick(self):
        self.done_pulse = False
        if not self.busy:
            return

        self.cycle_count += 1
        self.cycles_left -= 1

        if self.cycles_left <= 0:
            row = None if self.current_job is None else self.current_job["row"]
            total_cycles = self.cycle_count

            self.state = "IDLE"
            self.done_pulse = True

            self._trace(
                f"BUSY -> IDLE | done row={row} total_cycles={total_cycles}"
            )


if __name__ == "__main__":
    import os
    import sys

    ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if ROOT_DIR not in sys.path:
        sys.path.insert(0, ROOT_DIR)

    import config

    h = HintPackModule(config)
    h.start_job(row=0)
    while h.busy:
        h.tick()

    print("HintPack cycles:", h.cycle_count)