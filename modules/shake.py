class ShakeModule:
    def __init__(self, config):
        self.config = config
        self.state = "IDLE"
        self.cycle_count = 0
        
        self.current_round = 0
        self.state_cycles_left = 0
        self.squeeze_blocks_left = 0
        self.current_rate = 0  # 호출된 모드에 따른 Rate 저장용

    def start_hash(self, mode=128, squeeze_blocks=1):
        self.cycle_count = 0
        self.current_round = 0
        self.squeeze_blocks_left = squeeze_blocks
        
        # 모드에 따른 Rate 결정
        if mode == 128:
            self.current_rate = self.config.SHAKE128_RATE
        elif mode == 256:
            self.current_rate = self.config.SHAKE256_RATE
        else:
            raise ValueError("Unsupported SHAKE mode. Use 128 or 256.")
            
        # 1. ABSORB 단계 시작
        self.state = "ABSORB"
        self.state_cycles_left = self.current_rate // self.config.MEM_BANDWIDTH

    def tick(self):
        if self.state == "IDLE":
            return

        self.cycle_count += 1
        self.state_cycles_left -= 1

        if self.state_cycles_left <= 0:
            if self.state == "ABSORB":
                self.state = "PERM_STEP1"
                self.current_round = 0
                self.state_cycles_left = self.config.SHAKE_CYCLES_PER_STEP

            elif self.state == "PERM_STEP1":
                self.state = "PERM_STEP2"
                self.state_cycles_left = self.config.SHAKE_CYCLES_PER_STEP
                
            elif self.state == "PERM_STEP2":
                self.current_round += 1
                
                if self.current_round < self.config.SHAKE_ROUNDS:
                    self.state = "PERM_STEP1"
                    self.state_cycles_left = self.config.SHAKE_CYCLES_PER_STEP
                else:
                    self.state = "SQUEEZE"
                    self.state_cycles_left = self.current_rate // self.config.MEM_BANDWIDTH

            elif self.state == "SQUEEZE":
                self.squeeze_blocks_left -= 1
                
                if self.squeeze_blocks_left > 0:
                    self.state = "PERM_STEP1"
                    self.current_round = 0
                    self.state_cycles_left = self.config.SHAKE_CYCLES_PER_STEP
                else:
                    self.state = "IDLE"


if __name__ == "__main__":
    import sys
    import os

    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    import config

    print("=== SHAKE Module Standalone Test ===")
    shake = ShakeModule(config)
    
    # [테스트 1] SHAKE128 (Matrix A 생성 시)
    print("\n[1] Starting SHAKE128 Hash (1 block output)...")
    shake.start_hash(mode=128, squeeze_blocks=1)
    while shake.state != "IDLE":
        shake.tick()
    print(f"-> SHAKE128 Completed! Total Cycles: {shake.cycle_count}")
    # 예상: Absorb(21) + Perm(240) + Squeeze(21) = 282 사이클

    # [테스트 2] SHAKE256 (해싱 시)
    print("\n[2] Starting SHAKE256 Hash (1 block output)...")
    shake.start_hash(mode=256, squeeze_blocks=1)
    while shake.state != "IDLE":
        shake.tick()
    print(f"-> SHAKE256 Completed! Total Cycles: {shake.cycle_count}")
    # 예상: Absorb(17) + Perm(240) + Squeeze(17) = 274 사이클