# config.py
import math

# ==============================================================================
# Dilithium2 Parameters
# ==============================================================================
DILITHIUM_N = 256
DILITHIUM_Q = 8380417
DILITHIUM_K = 4
DILITHIUM_L = 4
DILITHIUM_TAU = 39
DILITHIUM_OMEGA = 80

# Bit widths used for rough unpack/pack modeling
DILITHIUM_T1_BITS = 10
DILITHIUM_Z_BITS = 18

# Common byte sizes
SEED_BYTES = 32
CRH_BYTES = 64

# Approximate Dilithium2 object sizes
PK_BYTES = 1312
SIG_BYTES = 2420
MSG_BYTES = 32

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

# ==========================================
# Hint / W1 packing / final compare
# ==========================================
USEHINT_PE_COUNT = 2
USEHINT_PIPELINE_STAGES = 2

# Dilithium2-specific packed size:
# polyw1_pack() outputs 192 bytes per polynomial
W1_PACKED_BYTES_PER_POLY = 192

# final challenge size (c') = 32 bytes
FINAL_CHALLENGE_BYTES = 32

# Convenience values for final hash sizing
TOTAL_W1_PACKED_BYTES = DILITHIUM_K * W1_PACKED_BYTES_PER_POLY
FINAL_HASH_INPUT_BYTES = CRH_BYTES + TOTAL_W1_PACKED_BYTES   # mu || packed_w1

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