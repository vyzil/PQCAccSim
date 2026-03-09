class PolyArithmeticUnit:
    def __init__(self, config):
        self.config = config
        self.state = "IDLE"
        self.cycle_count = 0
        self.state_cycles_left = 0
        self.current_mode = None

    def start_operation(self, mode):
        """
        Polynomial-wise Pointwise Operation
        Supporting modes:
        - "mac_add": w^ = A * z
        - "mac_sub": w^ - c * t1
        - "hint": w'_1 = UseHint(h, w - c * t1 * 2^d)
        """
        self.cycle_count = 0
        self.current_mode = mode
        
        valid_modes = ["mac_add", "mac_sub", "hint"]
        if mode not in valid_modes:
            raise ValueError(f"Unsupported PAU mode: {mode}")

        self.state = "CALC_POLY"
        
        poly_cycles = self.config.DILITHIUM_N // self.config.PAU_PE_COUNT
        self.state_cycles_left = poly_cycles + self.config.PAU_PIPELINE_STAGES

    def tick(self):
        if self.state == "IDLE":
            return

        self.cycle_count += 1
        self.state_cycles_left -= 1

        if self.state_cycles_left <= 0:
            if self.state == "CALC_POLY":
                self.state = "IDLE"



if __name__ == "__main__":
    import sys
    import os

    ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, ROOT_DIR)
    
    import config

    print("=== PAU (PolyArithmeticUnit) Module Test ===\n")
    pau = PolyArithmeticUnit(config)
    
    test_modes = ["mac_add", "mac_sub", "hint"]
    
    for mode in test_modes:
        print(f"[{mode.upper():>7}] Operation")
        pau.start_operation(mode=mode)
        
        while pau.state != "IDLE":
            pau.tick()
            
        print(f"  -> Total cycles: {pau.cycle_count}")