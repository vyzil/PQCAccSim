import sys
import os
import math

# Add root directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from modules.ntt import NTTModule
from modules.shake import ShakeModule
# Assume you added UniformSamplerModule in modules/sampler.py
from modules.sampler import SampleInBallModule, UniformSamplerModule 
from modules.pau import PolyArithmeticUnit
from modules.packers import PkUnpackerModule, SigUnpackerModule, PackerModule

class DilithiumVerifierSimulator:
    def __init__(self):
        # 1. Initialize all hardware units
        self.config = config
        self.ntt = NTTModule(config)
        self.shake = ShakeModule(config)
        
        # We use two different samplers for different stages
        self.matrix_a_sampler = UniformSamplerModule(config) 
        self.sample_in_ball = SampleInBallModule(config)
        
        self.pau = PolyArithmeticUnit(config)
        self.pk_unpacker = PkUnpackerModule(config)
        self.sig_unpacker = SigUnpackerModule(config)
        self.packer = PackerModule(config)

        self.global_cycle = 0

    def step(self):
        """ 
        Advance the entire hardware system by one clock cycle.
        All .tick() calls simulate parallel hardware execution.
        """
        self.global_cycle += 1
        
        # Parallel Ticks for all modules
        self.pk_unpacker.tick()
        self.sig_unpacker.tick()
        self.ntt.tick()
        self.pau.tick()
        self.packer.tick()
        self.matrix_a_sampler.tick()
        
        # SHAKE and SampleInBall (for Challenge) handshake
        shake_ready = (self.shake.state == "SQUEEZE")
        self.shake.tick()
        self.sample_in_ball.tick(shake_fifo_ready=shake_ready)

    def wait_until_idle(self, *modules):
        """ Advance cycles until the specified hardware units finish """
        while any(m.state != "IDLE" for m in modules):
            self.step()

    def run_verify_serial(self):
        """ 
        The Main Scheduler:
        Orchestrates the Dilithium2 Verification sequence with data dependency.
        """
        print(f"--- [Cycle {self.global_cycle:8}] Starting Dilithium2 Verification ---")

        # --- STEP 1: Public Key Unpack ---
        print(f"[{self.global_cycle:8}] Task: Unpacking Public Key (Internal)")
        self.pk_unpacker.start_unpack()
        self.wait_until_idle(self.pk_unpacker)

        # --- STEP 2: Signature Unpack (Parallel with Message Hash) ---
        print(f"[{self.global_cycle:8}] Task: Unpacking Signature & Hashing Message")
        self.sig_unpacker.start_unpack()
        # Start SHAKE256 for the initial message hash (CRH)
        self.shake.start_hash(mode=256, squeeze_blocks=1)
        self.wait_until_idle(self.sig_unpacker, self.shake)

        # --- STEP 3: Matrix A Expansion (Strict Sequential Dependency) ---
        # k * l = 16 polynomials. 5 SHAKE rounds each for rejection sampling.
        print(f"[{self.global_cycle:8}] Task: Expanding Matrix A (16 Polys)")
        for p in range(self.config.DILITHIUM_K * self.config.DILITHIUM_L):
            for s in range(5):
                # 1. Start SHAKE128 for pseudo-random bits
                self.shake.start_hash(mode=128, squeeze_blocks=1)
                self.wait_until_idle(self.shake)
                
                # 2. Start Uniform Sampler to filter coefficients
                self.matrix_a_sampler.start_sampling()
                self.wait_until_idle(self.matrix_a_sampler)
            
            if (p + 1) % 4 == 0:
                print(f"[{self.global_cycle:8}]  -> Row {(p+1)//4} of Matrix A ready.")

        # --- STEP 4: Forward NTT (Vector z: l=4) ---
        print(f"[{self.global_cycle:8}] Task: Forward NTT (Vector z, 4 Polys)")
        for _ in range(self.config.DILITHIUM_L):
            self.ntt.start_transform(is_intt=False)
            self.wait_until_idle(self.ntt)

        # --- STEP 5: Matrix-Vector Multiplication (k * l = 16) ---
        print(f"[{self.global_cycle:8}] Task: Matrix-Vector Mult (16 Pointwise Muls)")
        for _ in range(self.config.DILITHIUM_K * self.config.DILITHIUM_L):
            self.pau.start_operation(mode="mac_add")
            self.wait_until_idle(self.pau)

        # --- STEP 6: Inverse NTT (Vector w_hat: k=4) ---
        print(f"[{self.global_cycle:8}] Task: Inverse NTT (Vector w, 4 Polys)")
        for _ in range(self.config.DILITHIUM_K):
            self.ntt.start_transform(is_intt=True)
            self.wait_until_idle(self.ntt)

        # --- STEP 7: UseHint (Vector w: k=4) ---
        print(f"[{self.global_cycle:8}] Task: UseHint (4 Polys)")
        for _ in range(self.config.DILITHIUM_K):
            self.pau.start_operation(mode="hint")
            self.wait_until_idle(self.pau)

        # --- STEP 8: Final Challenge Hash & Comparison ---
        print(f"[{self.global_cycle:8}] Task: Final Challenge Generation")
        self.shake.start_hash(mode=256, squeeze_blocks=1)
        # Here we use SampleInBall for the challenge polynomial
        self.sample_in_ball.start_sampling(mode="prob")
        self.wait_until_idle(self.shake, self.sample_in_ball)

        print(f"\n--- [Cycle {self.global_cycle:8}] Verification Sequence Finished ---")
        return self.global_cycle

    def run_verify_parallel(self):
        print(f"--- [Cycle {self.global_cycle:8}] Starting Real Parallel Verification ---")

        # --- PHASE 1: PRE-PROCESSING (Overlapped) ---
        # PK 읽으면서 동시에 Signature도 읽고, 메시지 해싱도 시작!
        self.pk_unpacker.start_unpack()
        self.sig_unpacker.start_unpack()
        self.shake.start_hash(mode=256, squeeze_blocks=1)
        
        # [중요] 세 모듈이 모두 IDLE이 될 때까지 '동시에' step()을 돌림
        self.wait_until_idle(self.pk_unpacker, self.sig_unpacker, self.shake)

        # --- PHASE 2: Matrix A Expansion with Background NTT ---
        print(f"[{self.global_cycle:8}] Task: Matrix A (SHAKE) while Pre-NTT (z, t1)")
        
        # 1. 일단 NTT 유닛에 z[0] 변환 작업을 던져줍니다.
        self.ntt.start_transform(is_intt=False)
        
        # 2. 동시에 SHAKE에게 Matrix A[0][0] 생성을 던져줍니다.
        self.shake.start_hash(mode=128, squeeze_blocks=1)
        self.matrix_a_sampler.start_sampling()

        # 3. 이제 루프를 돌며 '누가 먼저 끝나든' 시간을 흐르게 합니다.
        # 이 루프 안에서 NTT(z)와 SHAKE(A)가 병렬로 처리됩니다!
        while self.ntt.state != "IDLE" or self.shake.state != "IDLE":
            self.step()
            
            # 만약 NTT가 먼저 끝났다면, 바로 다음 z[1]을 NTT 유닛에 넣어줍니다.
            # (SHAKE가 Matrix A를 만드는 2만 사이클 동안 NTT는 계속 바쁘게 돌아갑니다.)
            # if self.ntt.state == "IDLE" and 아직_NTT할게_남았다면:
            #     self.ntt.start_transform(...)

        # --- PHASE 3: On-the-fly PAU (Pipelining) ---
        # Matrix A[i][j]가 한 블록 나올 때마다 PAU를 돌리는 것도 
        # SHAKE의 다음 블록 생성과 겹칠 수 있습니다.
        for i in range(16):
            self.shake.start_hash(mode=128, squeeze_blocks=1)
            self.matrix_a_sampler.start_sampling()
            
            # SHAKE가 도는 동안 "이전"에 생성된 데이터를 PAU가 처리하게 할 수 있습니다.
            # 이것이 진정한 하드웨어 파이프라이닝입니다.
            while self.shake.state != "IDLE":
                self.step()
                if self.pau.state == "IDLE": # PAU가 놀고 있다면 일을 준다
                    self.pau.start_operation(mode="mac_add")


if __name__ == "__main__":
    sim = DilithiumVerifierSimulator()
    # total_latency = sim.run_verify_serial()
    total_latency = sim.run_verify_parallel()
    
    print(f"\n[ Performance Result ]")
    print(f"Total Latency: {total_latency} cycles")
    print(f"Simulated at : 100 MHz")
    print(f"Execution Time: {(total_latency / 100e6) * 1000:.3f} ms")