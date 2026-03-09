import math

class PkUnpackerModule:
    """ 
    Dedicated hardware block for fetching and unpacking the Public Key.
    Interfaces with the fast internal memory (e.g., Secure ROM/SRAM).
    """
    def __init__(self, config):
        self.config = config
        self.state = "IDLE"
        self.cycle_count = 0
        self.state_cycles_left = 0

    def start_unpack(self):
        self.cycle_count = 0
        self.state = "UNPACK_PK"
        
        rho_bits = self.config.SEED_BYTES * 8
        t1_bits = (self.config.DILITHIUM_K * self.config.DILITHIUM_N * self.config.DILITHIUM_T1_BITS)
        total_bits = rho_bits + t1_bits
        
        self.state_cycles_left = math.ceil(total_bits / self.config.MEM_BANDWIDTH)

    def tick(self):
        if self.state == "IDLE":
            return
        self.cycle_count += 1
        self.state_cycles_left -= 1
        if self.state_cycles_left <= 0:
            self.state = "IDLE"


class SigUnpackerModule:
    """ 
    Dedicated hardware block for fetching and unpacking the Signature.
    Interfaces with the slow external I/O (e.g., JTAG Mailbox or SPI).
    """
    def __init__(self, config):
        self.config = config
        self.state = "IDLE"
        self.cycle_count = 0
        self.state_cycles_left = 0

    def start_unpack(self):
        self.cycle_count = 0
        self.state = "UNPACK_SIG"
        
        c_tilde_bits = self.config.SEED_BYTES * 8
        z_bits = (self.config.DILITHIUM_L * self.config.DILITHIUM_N * self.config.DILITHIUM_Z_BITS)
        hint_bytes = self.config.DILITHIUM_OMEGA + self.config.DILITHIUM_K
        hint_bits = hint_bytes * 8
        total_bits = c_tilde_bits + z_bits + hint_bits
        
        self.state_cycles_left = math.ceil(total_bits / self.config.IO_BANDWIDTH)

    def tick(self):
        if self.state == "IDLE":
            return
        self.cycle_count += 1
        self.state_cycles_left -= 1
        if self.state_cycles_left <= 0:
            self.state = "IDLE"


class PackerModule:
    """ 
    Generic hardware block for packing data back into memory 
    or preparing data for output.
    """
    def __init__(self, config):
        self.config = config
        self.state = "IDLE"
        self.cycle_count = 0
        self.state_cycles_left = 0

    def start_pack(self, num_bits):
        self.cycle_count = 0
        self.state = "PACK_GENERIC"
        # Assuming packing writes to internal memory
        self.state_cycles_left = math.ceil(num_bits / self.config.MEM_BANDWIDTH)

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

    print("=== Isolated Unpacker/Packer Modules Test ===")
    
    pk_unpacker = PkUnpackerModule(config)
    pk_unpacker.start_unpack()
    while pk_unpacker.state != "IDLE":
        pk_unpacker.tick()
    print(f"PK Unpacker Cycles: {pk_unpacker.cycle_count}")
    
    sig_unpacker = SigUnpackerModule(config)
    sig_unpacker.start_unpack()
    while sig_unpacker.state != "IDLE":
        sig_unpacker.tick()
    print(f"Signature Unpacker Cycles: {sig_unpacker.cycle_count}")
    
    packer = PackerModule(config)
    packer.start_pack(num_bits=1024)
    while packer.state != "IDLE":
        packer.tick()
    print(f"Generic Packer Cycles (1024 bits): {packer.cycle_count}")