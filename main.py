# main.py
import os
import sys
from core.simulator import DilithiumVerifierSimulator


class Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for s in self.streams:
            s.write(data)
            s.flush()

    def flush(self):
        for s in self.streams:
            s.flush()


def main():

    os.makedirs("result", exist_ok=True)
    log_path = os.path.join("result", "result.log")

    logfile = open(log_path, "w")

    sys.stdout = Tee(sys.__stdout__, logfile)

    sim = DilithiumVerifierSimulator(message_bytes=32)

    total_cycles = sim.run(verbose=False)

    print("=== Dilithium Lightweight PQC Accelerator Simulation ===")
    print(f"Finished at cycle {total_cycles}")
    print(sim.report())
    print(sim.scheduler.debug_status())
    print(f"verify_pass (timing model): {sim.scheduler.verify_pass}")


if __name__ == "__main__":
    main()