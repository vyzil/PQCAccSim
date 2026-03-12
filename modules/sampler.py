# modules/sampler.py
import hashlib


class _ShakeByteStream:
    """
    Deterministic byte stream backed by Python hashlib SHAKE.

    We precompute on demand by asking for a longer digest whenever more bytes
    are required. This is fine for simulation and keeps the interface simple.
    """

    def __init__(self, mode: str, seed: bytes):
        if mode not in ("shake128", "shake256"):
            raise ValueError("mode must be 'shake128' or 'shake256'")
        self.mode = mode
        self.seed = seed

        self._cache = b""
        self._cursor = 0

    def _digest(self, nbytes: int) -> bytes:
        if self.mode == "shake128":
            return hashlib.shake_128(self.seed).digest(nbytes)
        return hashlib.shake_256(self.seed).digest(nbytes)

    def _ensure(self, nbytes_needed_from_cursor: int):
        target = self._cursor + nbytes_needed_from_cursor
        if len(self._cache) >= target:
            return
        self._cache = self._digest(target)

    def read(self, nbytes: int) -> bytes:
        self._ensure(nbytes)
        out = self._cache[self._cursor:self._cursor + nbytes]
        self._cursor += nbytes
        return out

    @property
    def bytes_consumed(self) -> int:
        return self._cursor


def _normalize_seed(seed, tag, default_prefix: bytes) -> bytes:
    """
    Make a deterministic seed from either explicit seed or tag.
    """
    if seed is not None:
        if isinstance(seed, bytes):
            return seed
        if isinstance(seed, str):
            return seed.encode("utf-8")
        return repr(seed).encode("utf-8")

    if tag is None:
        return default_prefix

    if isinstance(tag, bytes):
        return default_prefix + b"|" + tag
    if isinstance(tag, str):
        return default_prefix + b"|" + tag.encode("utf-8")
    return default_prefix + b"|" + repr(tag).encode("utf-8")


class UniformSamplerModule:
    """
    Rejection sampler for Matrix A generation.

    Philosophy
    ----------
    - Advances ONLY while SHAKE is in SQUEEZE state.
    - Each active cycle consumes one 72-bit chunk = 9 bytes.
    - Those 9 bytes are treated as actual SHAKE output.
    - We parse them exactly as 3 x 3-byte candidates.
    - For Dilithium-style uniform rejection, each candidate is reduced to 23 bits:
          t = b0 | b1<<8 | b2<<16
          t &= 0x7FFFFF
          accept if t < q
    - Done when 256 coefficients are accepted.

    This is no longer an average/approximate throughput model.
    Cycle count is determined by the actual random stream.
    """

    def __init__(self, config):
        self.config = config

        self.state = "IDLE"
        self.done_pulse = False
        self.cycle_count = 0

        self.accepted_coeffs = 0
        self.rejected_coeffs = 0
        self.current_job = None

        self.bytes_per_active_cycle = 9   # 72-bit stream
        self.candidates_per_cycle = 3

        self._stream = None
        self._poly = []

        self._cycle_getter = None

    @property
    def busy(self) -> bool:
        return self.state != "IDLE"

    @property
    def is_done(self) -> bool:
        return (
            self.state == "IDLE"
            and self.current_job is not None
            and self.accepted_coeffs >= self.config.DILITHIUM_N
        )

    @property
    def polynomial(self):
        return list(self._poly)

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
        print(f"[cycle {self._now():7d}] [UniformSampler  ] {msg}")

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------
    def reset(self):
        self.state = "IDLE"
        self.done_pulse = False
        self.cycle_count = 0
        self.accepted_coeffs = 0
        self.rejected_coeffs = 0
        self.current_job = None
        self._stream = None
        self._poly = []

    def start_sampling(self, seed=None, tag=None, stream_mode="shake128"):
        if self.busy:
            raise RuntimeError("UniformSamplerModule is busy")

        normalized_seed = _normalize_seed(seed, tag, b"uniform_sampler")
        self._stream = _ShakeByteStream(stream_mode, normalized_seed)

        self.state = "RUN"
        self.done_pulse = False
        self.cycle_count = 0
        self.accepted_coeffs = 0
        self.rejected_coeffs = 0
        self._poly = []

        self.current_job = {
            "type": "uniform_rejection",
            "tag": tag,
            "seed": normalized_seed,
            "stream_mode": stream_mode,
        }

        self._trace(
            f"IDLE -> RUN | start tag={tag} stream_mode={stream_mode}"
        )

    # ------------------------------------------------------------------
    # Sampling
    # ------------------------------------------------------------------
    def _consume_one_cycle_of_stream(self):
        """
        Consume one 72-bit chunk (9 bytes) and parse 3 candidates.
        """
        chunk = self._stream.read(self.bytes_per_active_cycle)

        for i in range(0, 9, 3):
            t = chunk[i] | (chunk[i + 1] << 8) | (chunk[i + 2] << 16)
            t &= 0x7FFFFF  # 23-bit candidate

            if t < self.config.DILITHIUM_Q:
                if self.accepted_coeffs < self.config.DILITHIUM_N:
                    self._poly.append(t)
                    self.accepted_coeffs += 1
            else:
                self.rejected_coeffs += 1

    def tick(self, shake_is_squeezing: bool):
        self.done_pulse = False

        if self.state == "IDLE":
            return

        if not shake_is_squeezing:
            return

        self.cycle_count += 1
        self._consume_one_cycle_of_stream()

        if self.accepted_coeffs >= self.config.DILITHIUM_N:
            self.accepted_coeffs = self.config.DILITHIUM_N
            self.state = "IDLE"
            self.done_pulse = True

            tag = None if self.current_job is None else self.current_job["tag"]
            bytes_consumed = 0 if self._stream is None else self._stream.bytes_consumed
            self._trace(
                f"RUN -> IDLE | done tag={tag} accepted={self.accepted_coeffs} "
                f"rejected={self.rejected_coeffs} bytes={bytes_consumed} cycles={self.cycle_count}"
            )

    def status(self):
        return {
            "module": "UniformSamplerModule",
            "state": self.state,
            "busy": self.busy,
            "is_done": self.is_done,
            "done_pulse": self.done_pulse,
            "cycle_count": self.cycle_count,
            "accepted_coeffs": self.accepted_coeffs,
            "rejected_coeffs": self.rejected_coeffs,
            "target_coeffs": self.config.DILITHIUM_N,
            "bytes_consumed": 0 if self._stream is None else self._stream.bytes_consumed,
            "current_job": self.current_job,
        }


class SampleInBallModule:
    """
    SampleInBall for challenge polynomial c.

    Philosophy
    ----------
    - Advances ONLY while SHAKE is in SQUEEZE state.
    - Each active cycle consumes one 72-bit chunk = 9 bytes.
    - Bytes are treated as actual SHAKE output bytes.
    - We follow the reference-style SampleInBall flow:

        1) Read 8 bytes of sign bits.
        2) For i in [N-TAU, ..., N-1]:
             repeatedly draw one byte b until b <= i
             c[i] = c[b]
             c[b] = +/-1 using next sign bit

    Notes
    -----
    - This is random-stream driven, not an average approximation.
    - The resulting cycle count depends on actual sampled bytes.
    """

    def __init__(self, config):
        self.config = config

        self.state = "IDLE"
        self.done_pulse = False
        self.cycle_count = 0

        self.accepted_positions = 0
        self.rejected_bytes = 0
        self.current_job = None

        self.bytes_per_active_cycle = 9  # 72-bit stream

        self._stream = None
        self._byte_queue = bytearray()

        self._signs_loaded = False
        self._signs = 0
        self._current_i = 0
        self._poly = []

        self._cycle_getter = None

    @property
    def busy(self) -> bool:
        return self.state != "IDLE"

    @property
    def is_done(self) -> bool:
        return (
            self.state == "IDLE"
            and self.current_job is not None
            and self.accepted_positions >= self.config.DILITHIUM_TAU
        )

    @property
    def polynomial(self):
        return list(self._poly)

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
        print(f"[cycle {self._now():7d}] [SampleInBall    ] {msg}")

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------
    def reset(self):
        self.state = "IDLE"
        self.done_pulse = False
        self.cycle_count = 0
        self.accepted_positions = 0
        self.rejected_bytes = 0
        self.current_job = None

        self._stream = None
        self._byte_queue = bytearray()

        self._signs_loaded = False
        self._signs = 0
        self._current_i = 0
        self._poly = []

    def start_sampling(self, seed=None, tag=None, stream_mode="shake256"):
        if self.busy:
            raise RuntimeError("SampleInBallModule is busy")

        normalized_seed = _normalize_seed(seed, tag, b"sample_in_ball")
        self._stream = _ShakeByteStream(stream_mode, normalized_seed)

        self.state = "RUN"
        self.done_pulse = False
        self.cycle_count = 0
        self.accepted_positions = 0
        self.rejected_bytes = 0

        self._byte_queue = bytearray()
        self._signs_loaded = False
        self._signs = 0
        self._current_i = self.config.DILITHIUM_N - self.config.DILITHIUM_TAU
        self._poly = [0] * self.config.DILITHIUM_N

        self.current_job = {
            "type": "sample_in_ball",
            "tag": tag,
            "seed": normalized_seed,
            "stream_mode": stream_mode,
        }

        self._trace(
            f"IDLE -> RUN | start tag={tag} stream_mode={stream_mode}"
        )

    # ------------------------------------------------------------------
    # Sampling
    # ------------------------------------------------------------------
    def _refill_one_cycle_of_stream(self):
        self._byte_queue.extend(self._stream.read(self.bytes_per_active_cycle))

    def _maybe_load_signs(self):
        if self._signs_loaded:
            return
        if len(self._byte_queue) < 8:
            return

        sign_bytes = bytes(self._byte_queue[:8])
        del self._byte_queue[:8]

        self._signs = int.from_bytes(sign_bytes, byteorder="little")
        self._signs_loaded = True

    def _process_available_bytes(self):
        """
        Process as many bytes as possible from current queue.
        """
        self._maybe_load_signs()
        if not self._signs_loaded:
            return

        while self._current_i < self.config.DILITHIUM_N and len(self._byte_queue) >= 1:
            b = self._byte_queue[0]
            del self._byte_queue[0]

            if b > self._current_i:
                self.rejected_bytes += 1
                continue

            # accept this byte for current i
            self._poly[self._current_i] = self._poly[b]
            self._poly[b] = 1 if (self._signs & 1) == 0 else -1
            self._signs >>= 1

            self._current_i += 1
            self.accepted_positions += 1

            if self.accepted_positions >= self.config.DILITHIUM_TAU:
                break

    def tick(self, shake_is_squeezing: bool):
        self.done_pulse = False

        if self.state == "IDLE":
            return

        if not shake_is_squeezing:
            return

        self.cycle_count += 1
        self._refill_one_cycle_of_stream()
        self._process_available_bytes()

        if self.accepted_positions >= self.config.DILITHIUM_TAU:
            self.accepted_positions = self.config.DILITHIUM_TAU
            self.state = "IDLE"
            self.done_pulse = True

            tag = None if self.current_job is None else self.current_job["tag"]
            bytes_consumed = 0 if self._stream is None else self._stream.bytes_consumed
            self._trace(
                f"RUN -> IDLE | done tag={tag} accepted={self.accepted_positions} "
                f"rejected_bytes={self.rejected_bytes} bytes={bytes_consumed} cycles={self.cycle_count}"
            )

    def status(self):
        return {
            "module": "SampleInBallModule",
            "state": self.state,
            "busy": self.busy,
            "is_done": self.is_done,
            "done_pulse": self.done_pulse,
            "cycle_count": self.cycle_count,
            "accepted_positions": self.accepted_positions,
            "rejected_bytes": self.rejected_bytes,
            "target_positions": self.config.DILITHIUM_TAU,
            "bytes_consumed": 0 if self._stream is None else self._stream.bytes_consumed,
            "current_i": self._current_i,
            "current_job": self.current_job,
        }


if __name__ == "__main__":
    import os
    import sys

    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import config

    print("=== sampler.py standalone test ===")

    # ------------------------------------------------------------
    # Uniform sampler test
    # ------------------------------------------------------------
    u = UniformSamplerModule(config)
    u.start_sampling(seed=b"A_seed_example", tag="A[0][0]", stream_mode="shake128")

    while not u.is_done:
        u.tick(shake_is_squeezing=True)

    print("\n[UniformSamplerModule]")
    print(f"cycle_count      : {u.cycle_count}")
    print(f"accepted_coeffs  : {u.accepted_coeffs}")
    print(f"rejected_coeffs  : {u.rejected_coeffs}")
    print(f"bytes_consumed   : {u.status()['bytes_consumed']}")
    print(f"poly_len         : {len(u.polynomial)}")

    # ------------------------------------------------------------
    # SampleInBall test
    # ------------------------------------------------------------
    s = SampleInBallModule(config)
    s.start_sampling(seed=b"c_seed_example", tag="c", stream_mode="shake256")

    while not s.is_done:
        s.tick(shake_is_squeezing=True)

    nonzero = sum(1 for x in s.polynomial if x != 0)

    print("\n[SampleInBallModule]")
    print(f"cycle_count        : {s.cycle_count}")
    print(f"accepted_positions : {s.accepted_positions}")
    print(f"rejected_bytes     : {s.rejected_bytes}")
    print(f"bytes_consumed     : {s.status()['bytes_consumed']}")
    print(f"nonzero_coeffs     : {nonzero}")