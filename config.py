import math

# ==========================================
# PQC (CRYSTALS-Dilithium) Parameters
# ==========================================
DILITHIUM_Q = 8380417
DILITHIUM_N = 256
DILITHIUM_K = 4
DILITHIUM_L = 4
DILITHIUM_TAU = 39
DILITHIUM_OMEGA = 80

# ==========================================
# NTT Module Parameters
# ==========================================
NTT_TOTAL_STAGES = int(math.log2(DILITHIUM_N))
NTT_STAGES_PER_PASS = 2
NTT_PASSES = NTT_TOTAL_STAGES // NTT_STAGES_PER_PASS

NTT_CHUNK_SIZE = 4      # Number of data processed in one pipeline chunk
NTT_CHUNK_CYCLES = 2    # Cycles taken to process one chunk (Stage1 + Stage2)
NTT_DATA_FETCH = 2      # Number of data items fetched per cycle for NTT processing

NTT_BU_COUNT = 2

# ==========================================
# SHAKE Module Parameters
# ==========================================
SHAKE_STATE_BITS = 1600
SHAKE_DATAPATH_BITS = 320
SHAKE_ROUNDS = 24

SHAKE_STEPS_PER_ROUND = 2
SHAKE_CYCLES_PER_STEP = SHAKE_STATE_BITS // SHAKE_DATAPATH_BITS 

SHAKE128_RATE = 1344
SHAKE256_RATE = 1088 

# ==========================================
# Sampler Module Parameters
# ==========================================
SAMPLER_MAX_REJECT_CYCLES = 128


# ==========================================
# PAU (Polynomial Arithmetic Unit) Parameters
# ==========================================
PAU_PE_COUNT = 2           # 1사이클에 처리할 계수(Coefficient)의 개수
PAU_PIPELINE_STAGES = 3    # Fetch -> Execute(Mul/Add/Shift/Hint) -> Writeback

# ==========================================
# Data Bit-widths for Packing/Unpacking
# ==========================================
DILITHIUM_T1_BITS = 10
DILITHIUM_Z_BITS  = 20
SEED_BYTES        = 32

# ==========================================
# Bandwidth Parameters
# ==========================================
MEM_BANDWIDTH = 64
IO_BANDWIDTH = 32