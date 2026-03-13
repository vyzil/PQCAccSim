# PQCAccSim

Cycle-level timing simulator for a lightweight CRYSTALS-Dilithium verifier accelerator.

## Requirements

The dependency file name is correct: `requirements.txt`.

Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

## Run Simulation

From project root:

```bash
python3 main.py
```

This writes a mode-specific log in `result/`.

### Scheduler/Level Selection

```bash
python3 main.py --level default
python3 main.py --level 2
python3 main.py --level 3
python3 main.py --level 5
```

- `default` -> `DilithiumScheduler`
- `2` -> `Dilithium2Scheduler`
- `3` -> `Dilithium3Scheduler`
- `5` -> `Dilithium5Scheduler`

Log files are generated as:

- `result/result_default.log`
- `result/result_d2.log`
- `result/result_d3.log`
- `result/result_d5.log`

You can also override the log file path:

```bash
python3 main.py --level 3 --log result/custom_d3.log
```

## Generate Timeline Workbook

From `result/` directory:

```bash
cd result
python3 make_timeline.py --level 3
```

Or provide explicit input/output paths:

```bash
python3 make_timeline.py --log result_d3.log --out module_timeline_d3.xlsx
```

## Notes

- `.xlsx` timeline outputs are ignored by git (`result/*.xlsx`).
- `.log` files are ignored by git (`*.log`).
- The simulator reports timing/performance behavior, not full cryptographic functional verification.
