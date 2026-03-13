# main.py
import os
import sys
import argparse
from core.simulator import DilithiumVerifierSimulator
from core.scheduler import (
    DilithiumScheduler,
    Dilithium2Scheduler,
    Dilithium3Scheduler,
    Dilithium5Scheduler,
)


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
    parser = argparse.ArgumentParser(description="Dilithium lightweight accelerator simulator")
    parser.add_argument(
        "--level",
        default="default",
        choices=["default", "2", "3", "5"],
        help="Scheduler level selection: default, 2, 3, 5",
    )
    parser.add_argument(
        "--log",
        default=None,
        help="Optional explicit log file path",
    )
    args = parser.parse_args()

    scheduler_map = {
        "default": DilithiumScheduler,
        "2": Dilithium2Scheduler,
        "3": Dilithium3Scheduler,
        "5": Dilithium5Scheduler,
    }
    scheduler_cls = scheduler_map[args.level]

    os.makedirs("result", exist_ok=True)
    mode_tag = f"d{args.level}" if args.level in {"2", "3", "5"} else "default"
    log_path = args.log or os.path.join("result", f"result_{mode_tag}.log")

    logfile = open(log_path, "w")

    sys.stdout = Tee(sys.__stdout__, logfile)

    sim = DilithiumVerifierSimulator(message_bytes=32, scheduler_cls=scheduler_cls)

    total_cycles = sim.run(verbose=False)

    print("=== Dilithium Lightweight PQC Accelerator Simulation ===")
    print(f"Scheduler mode: {args.level}")
    print(f"Log file      : {log_path}")
    print(f"Finished at cycle {total_cycles}")
    print(sim.report())
    print(sim.scheduler.debug_status())
    print(f"verify_pass (timing model): {sim.scheduler.verify_pass}")


if __name__ == "__main__":
    main()
