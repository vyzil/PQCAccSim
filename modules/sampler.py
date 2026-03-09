import random

class SampleInBallModule:
    def __init__(self, config):
        self.config = config
        self.state = "IDLE"
        self.cycle_count = 0
        self.tau = self.config.DILITHIUM_TAU
        
        self.i_counter = 0
        self.reject_cycle_counter = 0
        self.mode = "prob"

    def start_sampling(self, mode="prob"):
        """
        mode: "min" (Best-case) / "max" (Worst-case) / "prob" (Probabilistic)
        """
        self.cycle_count = 0
        self.mode = mode
        self.state = "INIT_ZERO"

    def tick(self, shake_fifo_ready=False):
        if self.state == "IDLE":
            return

        self.cycle_count += 1

        if self.state == "INIT_ZERO":   
            # using 1 cycle to reset 512-bit register
            self.state = "WAIT_FOR_SHAKE"
            
        elif self.state == "WAIT_FOR_SHAKE":
            # Wait unitil SHAKE module produces the first block
            if shake_fifo_ready:
                self.state = "FETCH_SIGNS"

        elif self.state == "FETCH_SIGNS":
            self.state = "REJECTION_SAMPLING"
            self.i_counter = self.config.DILITHIUM_N - self.tau

        elif self.state == "REJECTION_SAMPLING":
            if self.mode == "min":
                self.i_counter += 1
                if self.i_counter >= self.config.DILITHIUM_N:
                    self.state = "IDLE"
                return
            
            if self.mode == "max":
                self.reject_cycle_counter += 1
                if self.reject_cycle_counter >= self.config.SAMPLER_MAX_REJECT_CYCLES:
                    self.state = "IDLE"
                return

            if self.mode == "prob":
                self.reject_cycle_counter += 1
                j = random.randint(0, 255)
                
                if j <= self.i_counter:
                    self.i_counter += 1
                    
                if self.i_counter >= self.config.DILITHIUM_N:
                    self.state = "IDLE"

class UniformSamplerModule:
    """
    Hardware module for Uniform Rejection Sampling used in Matrix A expansion.
    Converts SHAKE128 output bits into coefficients in [0, Q-1].
    """
    def __init__(self, config):
        self.config = config
        self.state = "IDLE"
        self.cycle_count = 0
        self.state_cycles_left = 0

    def start_sampling(self):
        """
        Starts processing one block of SHAKE128 output (168 bytes / 1344 bits).
        One SHAKE128 block can produce up to 1344/24 = 56 potential coefficients.
        """
        self.cycle_count = 0
        self.state = "SAMPLING"
        
        # In hardware, we process coefficients in parallel or pipelined.
        # Let's assume a pipelined architecture where it takes N/Parallelism cycles.
        # For a single SHAKE block processing, it's roughly 50-60 cycles.
        self.state_cycles_left = 64 # Approximation for one SHAKE block's worth of sampling
        
    def tick(self):
        if self.state == "IDLE":
            return

        self.cycle_count += 1
        self.state_cycles_left -= 1

        if self.state_cycles_left <= 0:
            self.state = "IDLE"

            

if __name__ == "__main__":
    import sys
    import os

    ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, ROOT_DIR)
    import config

    print("=== SampleInBall (2-bit Packed) Module Test ===\n")
    
   # 1. MIN
    sampler_min = SampleInBallModule(config)
    sampler_min.start_sampling(mode="min")
    while sampler_min.state != "IDLE":
        sampler_min.tick(shake_fifo_ready=True)
    print(f"[MIN Mode]  Best-Case Cycles:  {sampler_min.cycle_count}")

    # 2. MAX
    sampler_max = SampleInBallModule(config)
    sampler_max.start_sampling(mode="max")
    while sampler_max.state != "IDLE":
        sampler_max.tick(shake_fifo_ready=True)
    print(f"[MAX Mode]  Worst-Case Cycles: {sampler_max.cycle_count}")

    # 3. PROB
    sampler_prob = SampleInBallModule(config)
    sampler_prob.start_sampling(mode="prob")
    while sampler_prob.state != "IDLE":
        sampler_prob.tick(shake_fifo_ready=True)
    print(f"[PROB Mode] Average Cycles:    {sampler_prob.cycle_count}")