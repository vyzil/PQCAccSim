# modules/shake.py
import math


class ShakeModule:
    """
    SHAKE timing model with multi-block absorb support.

    Main external API:
        - start_hash(mode, input_bytes, squeeze_blocks=1, tag=None)
        - tick()
        - busy
        - done_pulse
        - state

    Automatic flow:
        ABSORB(block 1) -> PERMUTE
        ABSORB(block 2) -> PERMUTE
        ...
        ABSORB(block N) -> PERMUTE
        SQUEEZE(block 1)
        [PERMUTE -> SQUEEZE(block 2)] ...
        [PERMUTE -> SQUEEZE(block M)]

    Notes
    -----
    - This is still a timing model, not a functional Keccak implementation.
    - For long inputs, absorb is split into rate-sized blocks.
    - Each absorb block is followed by one permutation.
    - If squeeze_blocks > 1, additional squeeze blocks require extra permutations.
    - Sampler overlap is modeled outside this module:
        sampler.tick(...) should only advance while self.state == "SQUEEZE".
    """

    def __init__(self, config):
        self.config = config

        self.state = "IDLE"
        self.cycle_count = 0
        self.state_cycles_left = 0
        self.done_pulse = False

        self.current_rate_bits = 0
        self.current_job = None

        self.squeeze_blocks_total = 0
        self.squeeze_blocks_done = 0

        self.absorb_blocks_total = 0
        self.absorb_block_index = 0  # 0-based
        self.input_bytes_total = 0

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
        print(f"[cycle {self._now():7d}] [SHAKE           ] {msg}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _get_rate_bits(self, mode: int) -> int:
        if mode == 128:
            return self.config.SHAKE128_RATE
        if mode == 256:
            return self.config.SHAKE256_RATE
        raise ValueError("Unsupported SHAKE mode. Use 128 or 256.")

    def _get_rate_bytes(self, mode: int) -> int:
        return self._get_rate_bits(mode) // 8

    def _absorb_cycles_for_bytes(self, num_bytes: int) -> int:
        num_bits = num_bytes * 8
        bw_bits = self.config.MEM_BANDWIDTH
        return (num_bits + bw_bits - 1) // bw_bits

    def _permute_cycles(self) -> int:
        return self.config.SHAKE_ROUNDS * self.config.SHAKE_CYCLES_PER_ROUND

    def _squeeze_cycles_per_block(self, mode: int) -> int:
        rate_bits = self._get_rate_bits(mode)
        bw_bits = self.config.SHAKE_SQUEEZE_BW_BITS
        return (rate_bits + bw_bits - 1) // bw_bits

    def _compute_absorb_blocks(self, mode: int, input_bytes: int) -> int:
        rate_bytes = self._get_rate_bytes(mode)
        # Even empty input would still require one padded absorb block in a real sponge.
        return max(1, math.ceil(input_bytes / rate_bytes))

    def _current_absorb_block_bytes(self, mode: int) -> int:
        """
        Bytes carried by the current absorb block.
        For the last block this may be partial.
        """
        rate_bytes = self._get_rate_bytes(mode)
        start = self.absorb_block_index * rate_bytes
        remaining = max(0, self.input_bytes_total - start)
        if remaining <= 0:
            # padding-only block for empty input corner case
            return 0
        return min(rate_bytes, remaining)

    def _enter_absorb_current_block(self, mode: int):
        old = self.state
        block_bytes = self._current_absorb_block_bytes(mode)
        self.state = "ABSORB"
        self.state_cycles_left = self._absorb_cycles_for_bytes(block_bytes)
        self._trace(
            f"{old} -> ABSORB | block={self.absorb_block_index + 1}/{self.absorb_blocks_total} "
            f"bytes={block_bytes} cycles={self.state_cycles_left}"
        )

    def _enter_permute(self):
        old = self.state
        self.state = "PERMUTE"
        self.state_cycles_left = self._permute_cycles()
        self._trace(
            f"{old} -> PERMUTE | cycles={self.state_cycles_left}"
        )

    def _enter_squeeze(self, mode: int):
        old = self.state
        self.state = "SQUEEZE"
        self.state_cycles_left = self._squeeze_cycles_per_block(mode)
        self._trace(
            f"{old} -> SQUEEZE | block={self.squeeze_blocks_done + 1}/{self.squeeze_blocks_total} "
            f"cycles={self.state_cycles_left}"
        )

    # ------------------------------------------------------------------
    # Main high-level API
    # ------------------------------------------------------------------
    def start_hash(self, mode=128, input_bytes=0, squeeze_blocks=1, tag=None):
        if self.busy:
            raise RuntimeError("SHAKE module is busy")
        if squeeze_blocks <= 0:
            raise ValueError("squeeze_blocks must be >= 1")

        self.current_rate_bits = self._get_rate_bits(mode)
        self.current_job = {
            "type": "hash",
            "mode": mode,
            "input_bytes": input_bytes,
            "squeeze_blocks": squeeze_blocks,
            "tag": tag,
        }

        self.cycle_count = 0
        self.done_pulse = False

        self.input_bytes_total = input_bytes
        self.absorb_blocks_total = self._compute_absorb_blocks(mode, input_bytes)
        self.absorb_block_index = 0

        self.squeeze_blocks_total = squeeze_blocks
        self.squeeze_blocks_done = 0

        self._trace(
            f"start_hash | mode=SHAKE{mode} input_bytes={input_bytes} "
            f"absorb_blocks={self.absorb_blocks_total} squeeze_blocks={squeeze_blocks} tag={tag}"
        )
        self._enter_absorb_current_block(mode)

    def estimate_cycles(self, mode=128, input_bytes=0, squeeze_blocks=1) -> int:
        if squeeze_blocks <= 0:
            raise ValueError("squeeze_blocks must be >= 1")

        absorb_blocks = self._compute_absorb_blocks(mode, input_bytes)
        absorb_transfer_cycles = self._absorb_cycles_for_bytes(input_bytes)

        permute_cycles_total = (
            absorb_blocks + (squeeze_blocks - 1)
        ) * self._permute_cycles()

        squeeze_cycles_total = squeeze_blocks * self._squeeze_cycles_per_block(mode)

        return absorb_transfer_cycles + permute_cycles_total + squeeze_cycles_total

    # ------------------------------------------------------------------
    # Optional manual API for debugging
    # ------------------------------------------------------------------
    def start_absorb(self, mode=128, input_bytes=0):
        if self.busy:
            raise RuntimeError("SHAKE module is busy")

        self.current_rate_bits = self._get_rate_bits(mode)
        self.current_job = {
            "type": "manual_absorb",
            "mode": mode,
            "input_bytes": input_bytes,
            "squeeze_blocks": 0,
            "tag": None,
        }
        self.cycle_count = 0
        self.done_pulse = False

        self.input_bytes_total = input_bytes
        self.absorb_blocks_total = 1
        self.absorb_block_index = 0
        self.squeeze_blocks_total = 0
        self.squeeze_blocks_done = 0

        self._trace(f"start_absorb | mode=SHAKE{mode} input_bytes={input_bytes}")
        self._enter_absorb_current_block(mode)

    def start_permute(self):
        if self.busy:
            raise RuntimeError("SHAKE module is busy")

        self.current_job = {
            "type": "manual_permute",
            "mode": None,
            "input_bytes": 0,
            "squeeze_blocks": 0,
            "tag": None,
        }
        self.cycle_count = 0
        self.done_pulse = False
        self.absorb_blocks_total = 0
        self.absorb_block_index = 0
        self.squeeze_blocks_total = 0
        self.squeeze_blocks_done = 0

        self._trace("start_permute")
        self._enter_permute()

    def start_squeeze(self, mode=128):
        if self.busy:
            raise RuntimeError("SHAKE module is busy")

        self.current_rate_bits = self._get_rate_bits(mode)
        self.current_job = {
            "type": "manual_squeeze",
            "mode": mode,
            "input_bytes": 0,
            "squeeze_blocks": 1,
            "tag": None,
        }
        self.cycle_count = 0
        self.done_pulse = False
        self.absorb_blocks_total = 0
        self.absorb_block_index = 0
        self.squeeze_blocks_total = 1
        self.squeeze_blocks_done = 0

        self._trace(f"start_squeeze | mode=SHAKE{mode}")
        self._enter_squeeze(mode)

    # ------------------------------------------------------------------
    # Advance one cycle
    # ------------------------------------------------------------------
    def tick(self):
        self.done_pulse = False

        if self.state == "IDLE":
            return

        self.cycle_count += 1
        self.state_cycles_left -= 1

        if self.state_cycles_left > 0:
            return

        # manual mode: stop immediately after one phase
        if self.current_job is not None and self.current_job["type"].startswith("manual_"):
            old = self.state
            total_cycles = self.cycle_count
            self.state = "IDLE"
            self.done_pulse = True
            self._trace(
                f"{old} -> IDLE | manual done total_cycles={total_cycles}"
            )
            return

        if self.current_job is None:
            old = self.state
            total_cycles = self.cycle_count
            self.state = "IDLE"
            self.done_pulse = True
            self._trace(
                f"{old} -> IDLE | done(no current_job) total_cycles={total_cycles}"
            )
            return

        mode = self.current_job["mode"]

        if self.state == "ABSORB":
            self._enter_permute()
            return

        if self.state == "PERMUTE":
            # If not all absorb blocks have been processed yet, go to next absorb block.
            if self.absorb_block_index + 1 < self.absorb_blocks_total:
                self.absorb_block_index += 1
                self._enter_absorb_current_block(mode)
                return

            # Otherwise, go to squeeze phase.
            self._enter_squeeze(mode)
            return

        if self.state == "SQUEEZE":
            self.squeeze_blocks_done += 1

            if self.squeeze_blocks_done < self.squeeze_blocks_total:
                self._trace(
                    f"SQUEEZE block complete | completed={self.squeeze_blocks_done}/{self.squeeze_blocks_total}"
                )
                self._enter_permute()
                return

            total_cycles = self.cycle_count
            tag = self.current_job["tag"]
            self.state = "IDLE"
            self.done_pulse = True
            self._trace(
                f"SQUEEZE -> IDLE | done total_cycles={total_cycles} tag={tag}"
            )
            return

    def status(self):
        return {
            "state": self.state,
            "busy": self.busy,
            "cycle_count": self.cycle_count,
            "state_cycles_left": self.state_cycles_left,
            "done_pulse": self.done_pulse,
            "current_rate_bits": self.current_rate_bits,
            "absorb_blocks_total": self.absorb_blocks_total,
            "absorb_block_index": self.absorb_block_index,
            "squeeze_blocks_total": self.squeeze_blocks_total,
            "squeeze_blocks_done": self.squeeze_blocks_done,
            "current_job": self.current_job,
        }


if __name__ == "__main__":
    import sys
    import os

    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import config

    shake = ShakeModule(config)

    print("=== SHAKE Test ===")

    # A polynomial generation example
    est = shake.estimate_cycles(mode=128, input_bytes=34, squeeze_blocks=5)
    print(f"Estimated SHAKE128(A poly): {est} cycles")

    shake.start_hash(mode=128, input_bytes=34, squeeze_blocks=5, tag="A_poly")
    while shake.busy:
        shake.tick()
    print(f"Actual cycles: {shake.cycle_count}")

    # Final challenge example for Dilithium2:
    # mu(64B) + packed w1 (4 * 192B) = 832B
    final_input = 64 + 4 * 192
    est_final = shake.estimate_cycles(mode=256, input_bytes=final_input, squeeze_blocks=1)
    print(f"Estimated SHAKE256(mu||w1): {est_final} cycles")

    shake.start_hash(mode=256, input_bytes=final_input, squeeze_blocks=1, tag="c_prime")
    while shake.busy:
        shake.tick()
    print(f"Actual final SHAKE cycles: {shake.cycle_count}")