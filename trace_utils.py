# trace_utils.py

def trace_print(enabled: bool, cycle: int, who: str, msg: str):
    if not enabled:
        return
    print(f"[cycle {cycle:7d}] [{who:16s}] {msg}")