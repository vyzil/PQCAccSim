# config.py
import math

# ==============================================================================
# Dilithium Parameters
# ==============================================================================
DILITHIUM_N = 256
DILITHIUM_Q = 8380417
DILITHIUM_LEVEL = 2

# Common byte sizes (shared across levels)
SEED_BYTES = 32
CRH_BYTES = 64
MSG_BYTES = 32

# Level-specific profiles used by scheduler/simulator.
# Fields here drive both dataflow dimensions (K,L,TAU,OMEGA) and byte sizing.
DILITHIUM_PROFILES = {
    2: {
        "K": 4,
        "L": 4,
        "TAU": 39,
        "OMEGA": 80,
        "PK_BYTES": 1312,
        "SIG_BYTES": 2420,
        "T1_BITS": 10,
        "Z_BITS": 18,
        "W1_PACKED_BYTES_PER_POLY": 192,
    },
    3: {
        "K": 6,
        "L": 5,
        "TAU": 49,
        "OMEGA": 55,
        "PK_BYTES": 1952,
        "SIG_BYTES": 3293,
        "T1_BITS": 10,
        "Z_BITS": 20,
        "W1_PACKED_BYTES_PER_POLY": 128,
    },
    5: {
        "K": 8,
        "L": 7,
        "TAU": 60,
        "OMEGA": 75,
        "PK_BYTES": 2592,
        "SIG_BYTES": 4595,
        "T1_BITS": 10,
        "Z_BITS": 20,
        "W1_PACKED_BYTES_PER_POLY": 128,
    },
}


def _apply_dilithium_profile(level: int) -> None:
    if level not in DILITHIUM_PROFILES:
        raise ValueError(f"Unsupported Dilithium level: {level}. Use one of {sorted(DILITHIUM_PROFILES.keys())}")

    p = DILITHIUM_PROFILES[level]

    global DILITHIUM_LEVEL
    global DILITHIUM_K, DILITHIUM_L, DILITHIUM_TAU, DILITHIUM_OMEGA
    global PK_BYTES, SIG_BYTES, DILITHIUM_T1_BITS, DILITHIUM_Z_BITS
    global W1_PACKED_BYTES_PER_POLY, TOTAL_W1_PACKED_BYTES, FINAL_HASH_INPUT_BYTES

    DILITHIUM_LEVEL = level
    DILITHIUM_K = p["K"]
    DILITHIUM_L = p["L"]
    DILITHIUM_TAU = p["TAU"]
    DILITHIUM_OMEGA = p["OMEGA"]
    PK_BYTES = p["PK_BYTES"]
    SIG_BYTES = p["SIG_BYTES"]
    DILITHIUM_T1_BITS = p["T1_BITS"]
    DILITHIUM_Z_BITS = p["Z_BITS"]
    W1_PACKED_BYTES_PER_POLY = p["W1_PACKED_BYTES_PER_POLY"]

    TOTAL_W1_PACKED_BYTES = DILITHIUM_K * W1_PACKED_BYTES_PER_POLY
    FINAL_HASH_INPUT_BYTES = CRH_BYTES + TOTAL_W1_PACKED_BYTES


def set_dilithium_level(level: int) -> None:
    _apply_dilithium_profile(level)

# ==============================================================================
# Memory / I/O
# ==============================================================================
MEM_BANDWIDTH = 64      # bits/cycle
IO_BANDWIDTH = 64       # bits/cycle

# ==============================================================================
# SHAKE
# ==============================================================================
SHAKE128_RATE = 1344    # bits = 168 bytes
SHAKE256_RATE = 1088    # bits = 136 bytes
SHAKE_ROUNDS = 24
SHAKE_CYCLES_PER_ROUND = 10
SHAKE_SQUEEZE_BW_BITS = 72   # internal output datapath for sampler side

# For A expansion
A_EXPAND_INPUT_BYTES = 34
A_EXPAND_BLOCKS_PER_POLY = 5

# ==========================================
# NTT Module Parameters
# ==========================================
NTT_TOTAL_STAGES = int(math.log2(DILITHIUM_N))   # 8
NTT_BU_COUNT = 2                                 # 2 butterfly ops / cycle
NTT_COEFF_FETCH_PER_CYCLE = 2                    # dual-port memory
NTT_TWIDDLE_MUL_PER_CYCLE = 2                    # 2 coeff pre/post mul per cycle

NTT_CORE_CYCLES = (DILITHIUM_N // 2) * NTT_TOTAL_STAGES // NTT_BU_COUNT
NTT_PREPOST_CYCLES = DILITHIUM_N // NTT_TWIDDLE_MUL_PER_CYCLE

# ==============================================================================
# PAU
# ==============================================================================
PAU_PE_COUNT = 2
PAU_PIPELINE_STAGES = 4
# If True, scheduler blocks issuing next z-NTT while PAU is processing mac_add_*.
# Use this when modeling that z buffer data must be retained until PAU job completes.
PAU_HOLD_Z_BUFFER_UNTIL_DONE = True

# ==========================================
# Hint / W1 packing / final compare
# ==========================================
USEHINT_PE_COUNT = 2
USEHINT_PIPELINE_STAGES = 2

# W1 packed bytes per polynomial is level dependent and set by profile.
W1_PACKED_BYTES_PER_POLY = 0

# final challenge size (c') = 32 bytes
FINAL_CHALLENGE_BYTES = 32

# Convenience values for final hash sizing (set by profile)
TOTAL_W1_PACKED_BYTES = 0
FINAL_HASH_INPUT_BYTES = 0

# ==============================================================================
# Optional reporting
# ==============================================================================
CLOCK_FREQUENCY_HZ = 100_000_000  # 100 MHz

# ------------------------------------------
# Debug / Trace
# ------------------------------------------
TRACE_ENABLED = True
TRACE_MODULE_STATES = True
TRACE_SCHEDULER = True
TRACE_CYCLE_STEPS = False

def ceil_div(a: int, b: int) -> int:
    return (a + b - 1) // b


# Initialize level-dependent parameters at import time.
_apply_dilithium_profile(DILITHIUM_LEVEL)
