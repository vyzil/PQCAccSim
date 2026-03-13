# core/simulator.py
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import config
from core.memory import MemorySystem
from core.scheduler import (
    DilithiumScheduler,
    Dilithium2Scheduler,
    Dilithium3Scheduler,
    Dilithium5Scheduler,
)
from modules.hint import HintPackModule
from modules.ntt import NTTModule
from modules.packers import PackerModule, PkUnpackerModule, SigUnpackerModule
from modules.pau import PolyArithmeticUnit
from modules.sampler import SampleInBallModule, UniformSamplerModule
from modules.shake import ShakeModule
from trace_utils import trace_print


class DilithiumVerifierSimulator:
    def __init__(self, message_bytes=None, scheduler_cls=None):
        if scheduler_cls is None:
            level = getattr(config, "DILITHIUM_LEVEL", None)
            if level == 2:
                scheduler_cls = Dilithium2Scheduler
            elif level == 3:
                scheduler_cls = Dilithium3Scheduler
            elif level == 5:
                scheduler_cls = Dilithium5Scheduler
            else:
                scheduler_cls = DilithiumScheduler

        # Keep config parameters synchronized with scheduler selection.
        if scheduler_cls is Dilithium2Scheduler:
            config.set_dilithium_level(2)
        elif scheduler_cls is Dilithium3Scheduler:
            config.set_dilithium_level(3)
        elif scheduler_cls is Dilithium5Scheduler:
            config.set_dilithium_level(5)

        self.config = config
        self.memory = MemorySystem(config, message_bytes=message_bytes)

        # ------------------------------------------------------------
        # Hardware modules
        # ------------------------------------------------------------
        self.ntt = NTTModule(config)
        self.shake = ShakeModule(config)
        self.matrix_a_sampler = UniformSamplerModule(config)
        self.sample_in_ball = SampleInBallModule(config)
        self.pau = PolyArithmeticUnit(config)
        self.hint = HintPackModule(config)

        self.pk_unpacker = PkUnpackerModule(config)
        self.sig_unpacker = SigUnpackerModule(config)
        self.packer = PackerModule(config)

        self.global_cycle = 0
        self.scheduler = scheduler_cls(self)

        # ------------------------------------------------------------
        # Give modules access to current cycle for internal trace logs
        # ------------------------------------------------------------
        modules = [
            self.ntt,
            self.shake,
            self.matrix_a_sampler,
            self.sample_in_ball,
            self.pau,
            self.hint,
            self.pk_unpacker,
            self.sig_unpacker,
            self.packer,
        ]

        for module in modules:
            if hasattr(module, "set_cycle_getter"):
                module.set_cycle_getter(self._get_cycle)

    # ------------------------------------------------------------------
    # Cycle getter for module trace
    # ------------------------------------------------------------------
    def _get_cycle(self):
        return self.global_cycle

    # ------------------------------------------------------------------
    # Trace helper
    # ------------------------------------------------------------------
    def trace(self, who: str, msg: str):
        trace_print(
            getattr(self.config, "TRACE_ENABLED", False),
            self.global_cycle,
            who,
            msg,
        )

    # ------------------------------------------------------------------
    # One hardware cycle
    # ------------------------------------------------------------------
    def step(self):
        self.global_cycle += 1

        # If SHAKE is already in SQUEEZE at the START of this cycle,
        # samplers may consume one 72-bit chunk during this same cycle.
        shake_is_squeezing = (self.shake.state == "SQUEEZE")

        # Optional ultra-verbose per-cycle trace
        if getattr(self.config, "TRACE_CYCLE_STEPS", False):
            self.trace(
                "SIM",
                (
                    f"step | shake={self.shake.state} "
                    f"ntt_busy={self.ntt.busy} "
                    f"pau_busy={self.pau.busy} "
                    f"hint_busy={self.hint.busy} "
                    f"squeeze={shake_is_squeezing}"
                ),
            )

        # Independent modules
        self.pk_unpacker.tick()
        self.sig_unpacker.tick()
        self.ntt.tick()
        self.pau.tick()
        self.hint.tick()
        self.packer.tick()

        # SHAKE
        self.shake.tick()

        # Samplers overlap with SHAKE squeeze stream
        self.matrix_a_sampler.tick(shake_is_squeezing=shake_is_squeezing)
        self.sample_in_ball.tick(shake_is_squeezing=shake_is_squeezing)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def any_module_busy(self) -> bool:
        modules = [
            self.pk_unpacker,
            self.sig_unpacker,
            self.ntt,
            self.shake,
            self.matrix_a_sampler,
            self.sample_in_ball,
            self.pau,
            self.hint,
            self.packer,
        ]
        return any(module.busy for module in modules)

    def run(self, verbose=False, max_cycles=10_000_000):
        self.trace("SIM", "run() start")
        total = self.scheduler.run(verbose=verbose, max_cycles=max_cycles)
        self.trace("SIM", f"run() done | total_cycles={total}")
        return total

    def report(self):
        clk = self.config.CLOCK_FREQUENCY_HZ
        elapsed_ms = (self.global_cycle / clk) * 1000.0

        return (
            "\n[Performance Report]\n"
            f"Total cycles   : {self.global_cycle}\n"
            f"Clock          : {clk / 1e6:.1f} MHz\n"
            f"Execution time : {elapsed_ms:.6f} ms\n"
            f"Memory regions : {self.memory.summary()}\n"
            f"Verify result  : {self.scheduler.verify_pass}\n"
        )


if __name__ == "__main__":
    sim = DilithiumVerifierSimulator(message_bytes=32)
    total_cycles = sim.run(verbose=False)

    print("=== Dilithium Lightweight PQC Accelerator Simulation ===")
    print(f"Finished at cycle {total_cycles}")
    print(sim.report())
    print(sim.scheduler.debug_status())
