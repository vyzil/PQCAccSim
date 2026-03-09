# modules/ntt.py

class NTTModule:
    def __init__(self, config):
        self.config = config
        self.state = "IDLE"
        self.cycle_count = 0
        
        self.state_cycles_left = 0
        self.current_pass = 0
        self.total_passes = self.config.NTT_PASSES

    def start_transform(self, is_intt=False):
        """Initialize and start NTT/INTT operation"""
        self.is_intt = is_intt
        self.cycle_count = 0
        self.current_pass = 0
        
        self.pipeline_setup_delay = self.config.NTT_CHUNK_SIZE // self.config.NTT_DATA_FETCH
        
        if not self.is_intt:
            self.state = "PRE_MUL"
            self.state_cycles_left = self.config.DILITHIUM_N // self.config.NTT_DATA_FETCH
        else:
            self.state = "CORE_CALC"
            self.state_cycles_left = (self.config.DILITHIUM_N // self.config.NTT_CHUNK_SIZE) * self.config.NTT_CHUNK_CYCLES

        self.cycle_count += self.pipeline_setup_delay

    def tick(self):
        """Execute one hardware clock cycle"""
        if self.state == "IDLE":
            return

        self.cycle_count += 1
        self.state_cycles_left -= 1

        if self.state_cycles_left <= 0:
            if self.state == "PRE_MUL":
                self.state = "CORE_CALC"
                self.current_pass = 0
                self.state_cycles_left = (self.config.DILITHIUM_N // self.config.NTT_CHUNK_SIZE) * self.config.NTT_CHUNK_CYCLES

            elif self.state == "CORE_CALC":
                self.current_pass += 1
                if self.current_pass < self.total_passes:
                    self.state_cycles_left = (self.config.DILITHIUM_N // self.config.NTT_CHUNK_SIZE) * self.config.NTT_CHUNK_CYCLES
                else:
                    if self.is_intt:
                        self.state = "POST_MUL"
                        self.state_cycles_left = self.config.DILITHIUM_N // self.config.NTT_DATA_FETCH
                    else:
                        self.state = "IDLE"

            elif self.state == "POST_MUL":
                self.state = "IDLE"




if __name__ == "__main__":
    import sys
    import os

    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    import config

    print("=== NTT Module Standalone Test ===")    
    ntt = NTTModule(config)
    
    print("\n[1] Starting NTT...")
    ntt.start_transform(is_intt=False)    
    while ntt.state != "IDLE":
        ntt.tick()
        # print(f"Cycle {ntt.cycle_count}: State = {ntt.state}, Chunks Left = {ntt.state_cycles_left}")        
    print(f"-> NTT Completed! Total Cycles: {ntt.cycle_count}")

    print("\n[2] Starting INTT...")
    ntt.start_transform(is_intt=True)    
    while ntt.state != "IDLE":
        ntt.tick()
        
    print(f"-> INTT Completed! Total Cycles: {ntt.cycle_count}")