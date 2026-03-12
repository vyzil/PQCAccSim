# main.py
from core.simulator import DilithiumVerifierSimulator


def main():
    sim = DilithiumVerifierSimulator(message_bytes=32)

    total_cycles = sim.run(verbose=False)

    print("=== Dilithium Lightweight PQC Accelerator Simulation ===")
    print(f"Finished at cycle {total_cycles}")
    print(sim.report())
    print(sim.scheduler.debug_status())
    print(f"verify_pass (timing model): {sim.scheduler.verify_pass}")


if __name__ == "__main__":
    main()