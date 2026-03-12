# modules/ntt.py

class NTTModule:
    """
    Simplified cycle model for 256-point NTT/INTT.

    Assumptions:
    - radix-2 NTT
    - total butterfly ops = (N/2) * log2(N)
    - 2 butterfly units => 2 butterfly ops / cycle
    - dual-port memory provides 2 coefficients / cycle
    - pre/post twiddle multiplication also processes 2 coeffs / cycle
    - fetch is sufficiently overlapped with computation after pipeline fill
    - no extra bank-conflict penalty is modeled
    """

    def __init__(self, config):
        self.config = config

        self.state = "IDLE"
        self.is_intt = False
        self.cycle_count = 0
        self.done_pulse = False
        self.state_cycles_left = 0
        self.current_job = None

        self._cycle_getter = None

    @property
    def busy(self):
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
        print(f"[cycle {self._now():7d}] [NTTModule       ] {msg}")

    # ------------------------------------------------------------------
    # Timing model
    # ------------------------------------------------------------------
    def core_cycles(self) -> int:
        return self.config.NTT_CORE_CYCLES

    def prepost_cycles(self) -> int:
        return self.config.NTT_PREPOST_CYCLES

    def estimate_cycles(self, is_intt: bool = False) -> int:
        return self.core_cycles() + self.prepost_cycles()

    def start_transform(self, is_intt: bool = False, tag=None):
        if self.busy:
            raise RuntimeError("NTT module is busy")

        self.is_intt = is_intt
        self.cycle_count = 0
        self.done_pulse = False
        self.current_job = {
            "type": "intt" if is_intt else "ntt",
            "tag": tag,
        }

        if is_intt:
            self.state = "CORE"
            self.state_cycles_left = self.core_cycles()
            self._trace(
                f"IDLE -> CORE | start INTT cycles={self.state_cycles_left} tag={tag}"
            )
        else:
            self.state = "PRE_MUL"
            self.state_cycles_left = self.prepost_cycles()
            self._trace(
                f"IDLE -> PRE_MUL | start NTT cycles={self.state_cycles_left} tag={tag}"
            )

    def tick(self):
        self.done_pulse = False

        if self.state == "IDLE":
            return

        self.cycle_count += 1
        self.state_cycles_left -= 1

        if self.state_cycles_left > 0:
            return

        if self.state == "PRE_MUL":
            self.state = "CORE"
            self.state_cycles_left = self.core_cycles()
            self._trace(
                f"PRE_MUL -> CORE | cycles={self.state_cycles_left} tag={self.current_job['tag'] if self.current_job else None}"
            )
            return

        if self.state == "CORE":
            if self.is_intt:
                self.state = "POST_MUL"
                self.state_cycles_left = self.prepost_cycles()
                self._trace(
                    f"CORE -> POST_MUL | cycles={self.state_cycles_left} tag={self.current_job['tag'] if self.current_job else None}"
                )
            else:
                done_tag = None if self.current_job is None else self.current_job["tag"]
                total_cycles = self.cycle_count
                self.state = "IDLE"
                self.done_pulse = True
                self._trace(
                    f"CORE -> IDLE | done NTT total_cycles={total_cycles} tag={done_tag}"
                )
            return

        if self.state == "POST_MUL":
            done_tag = None if self.current_job is None else self.current_job["tag"]
            total_cycles = self.cycle_count
            self.state = "IDLE"
            self.done_pulse = True
            self._trace(
                f"POST_MUL -> IDLE | done INTT total_cycles={total_cycles} tag={done_tag}"
            )
            return

    def status(self):
        return {
            "state": self.state,
            "is_intt": self.is_intt,
            "cycle_count": self.cycle_count,
            "state_cycles_left": self.state_cycles_left,
            "busy": self.busy,
            "done_pulse": self.done_pulse,
            "current_job": self.current_job,
        }


if __name__ == "__main__":
    import os
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import config

    ntt = NTTModule(config)

    ntt.start_transform(is_intt=False, tag="z0")
    while ntt.busy:
        ntt.tick()
    print(f"Forward NTT cycles: {ntt.cycle_count}")

    ntt.start_transform(is_intt=True, tag="w0")
    while ntt.busy:
        ntt.tick()
    print(f"Inverse NTT cycles: {ntt.cycle_count}")