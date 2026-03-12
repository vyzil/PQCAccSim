# modules/packers.py
import math


class PkUnpackerModule:
    """
    Reads pk from memory and unpacks it into local usable form.
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
        print(f"[cycle {self._now():7d}] [PkUnpacker      ] {msg}")

    # ------------------------------------------------------------------
    # Timing model
    # ------------------------------------------------------------------
    def start_unpack(self, num_bytes: int = None) -> None:
        if self.busy:
            raise RuntimeError("PkUnpackerModule is busy")

        num_bytes = num_bytes or self.config.PK_BYTES
        num_bits = num_bytes * 8

        self.current_job = {
            "type": "unpack_pk",
            "num_bytes": num_bytes,
        }
        self.cycles_left = math.ceil(num_bits / self.config.MEM_BANDWIDTH)
        self.cycle_count = 0
        self.done_pulse = False
        self.state = "BUSY"

        self._trace(
            f"IDLE -> BUSY | unpack_pk bytes={num_bytes} cycles={self.cycles_left}"
        )

    def tick(self) -> None:
        self.done_pulse = False
        if not self.busy:
            return

        self.cycle_count += 1
        self.cycles_left -= 1
        if self.cycles_left <= 0:
            total_cycles = self.cycle_count
            num_bytes = None if self.current_job is None else self.current_job["num_bytes"]

            self.state = "IDLE"
            self.done_pulse = True

            self._trace(
                f"BUSY -> IDLE | done unpack_pk bytes={num_bytes} total_cycles={total_cycles}"
            )


class SigUnpackerModule:
    """
    Reads signature from memory and unpacks it into local usable form.
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
        print(f"[cycle {self._now():7d}] [SigUnpacker     ] {msg}")

    # ------------------------------------------------------------------
    # Timing model
    # ------------------------------------------------------------------
    def start_unpack(self, num_bytes: int = None) -> None:
        if self.busy:
            raise RuntimeError("SigUnpackerModule is busy")

        num_bytes = num_bytes or self.config.SIG_BYTES
        num_bits = num_bytes * 8

        self.current_job = {
            "type": "unpack_sig",
            "num_bytes": num_bytes,
        }
        self.cycles_left = math.ceil(num_bits / self.config.IO_BANDWIDTH)
        self.cycle_count = 0
        self.done_pulse = False
        self.state = "BUSY"

        self._trace(
            f"IDLE -> BUSY | unpack_sig bytes={num_bytes} cycles={self.cycles_left}"
        )

    def tick(self) -> None:
        self.done_pulse = False
        if not self.busy:
            return

        self.cycle_count += 1
        self.cycles_left -= 1
        if self.cycles_left <= 0:
            total_cycles = self.cycle_count
            num_bytes = None if self.current_job is None else self.current_job["num_bytes"]

            self.state = "IDLE"
            self.done_pulse = True

            self._trace(
                f"BUSY -> IDLE | done unpack_sig bytes={num_bytes} total_cycles={total_cycles}"
            )


class PackerModule:
    """
    Generic output packer.
    Not critical for current verification flow, but useful for later extension.
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
        print(f"[cycle {self._now():7d}] [PackerModule    ] {msg}")

    # ------------------------------------------------------------------
    # Timing model
    # ------------------------------------------------------------------
    def start_pack(self, num_bits: int, tag=None) -> None:
        if self.busy:
            raise RuntimeError("PackerModule is busy")

        self.current_job = {
            "type": "pack",
            "num_bits": num_bits,
            "tag": tag,
        }
        self.cycles_left = math.ceil(num_bits / self.config.MEM_BANDWIDTH)
        self.cycle_count = 0
        self.done_pulse = False
        self.state = "BUSY"

        self._trace(
            f"IDLE -> BUSY | pack bits={num_bits} cycles={self.cycles_left} tag={tag}"
        )

    def tick(self) -> None:
        self.done_pulse = False
        if not self.busy:
            return

        self.cycle_count += 1
        self.cycles_left -= 1
        if self.cycles_left <= 0:
            total_cycles = self.cycle_count
            num_bits = None if self.current_job is None else self.current_job["num_bits"]
            tag = None if self.current_job is None else self.current_job["tag"]

            self.state = "IDLE"
            self.done_pulse = True

            self._trace(
                f"BUSY -> IDLE | done pack bits={num_bits} total_cycles={total_cycles} tag={tag}"
            )


if __name__ == "__main__":
    import sys
    import os

    ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if ROOT_DIR not in sys.path:
        sys.path.insert(0, ROOT_DIR)

    import config

    print("=== Pack/Unpack Test ===")

    pk = PkUnpackerModule(config)
    pk.start_unpack()
    while pk.busy:
        pk.tick()
    print(f"PK unpack cycles   : {pk.cycle_count}")

    sig = SigUnpackerModule(config)
    sig.start_unpack()
    while sig.busy:
        sig.tick()
    print(f"SIG unpack cycles  : {sig.cycle_count}")

    pack = PackerModule(config)
    pack.start_pack(num_bits=1024, tag="dummy")
    while pack.busy:
        pack.tick()
    print(f"Generic pack cycles: {pack.cycle_count}")