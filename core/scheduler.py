# core/scheduler.py
import math
from core.memory import BufferPool


class DilithiumScheduler:
    def __init__(self, sim):
        self.sim = sim
        self.cfg = sim.config
        self.buffers = BufferPool()

        # ------------------------------------------------------------
        # Global phase
        # ------------------------------------------------------------
        self.phase = "PREP"
        self.prep_stage = "UNPACK"
        self.prep_issued = False

        self.c_ready = False
        self.tr_ready = False
        self.mu_ready = False

        # paired challenge-c job
        self.challenge_pair_active = False

        # ------------------------------------------------------------
        # A generation
        # ------------------------------------------------------------
        self.total_a_polys = self.cfg.DILITHIUM_K * self.cfg.DILITHIUM_L
        self.next_a_index = 0
        self.a_pair_active = False
        self.a_inflight_tag = None

        # ------------------------------------------------------------
        # NTT/PAU
        # ------------------------------------------------------------
        self.row_mac_counts = [0] * self.cfg.DILITHIUM_K
        self.row_sub_done = [False] * self.cfg.DILITHIUM_K
        self.completed_w_rows = 0

        self.ntt_plan = self._build_ntt_plan()
        self.ntt_ptr = 0

        # ------------------------------------------------------------
        # Post processing after INTT
        # ------------------------------------------------------------
        self.post_queue = []
        self.packed_rows = 0
        self.packed_w1_bytes = 0

        # ------------------------------------------------------------
        # Final hash / compare
        # ------------------------------------------------------------
        self.final_hash_issued = False
        self.final_hash_done = False

        self.compare_active = False
        self.compare_cycles_left = 0
        self.compare_done = False
        self.verify_pass = None   # timing model only

    # ------------------------------------------------------------------
    # Trace helper
    # ------------------------------------------------------------------
    def _trace_enabled(self) -> bool:
        return getattr(self.cfg, "TRACE_ENABLED", False) and getattr(self.cfg, "TRACE_SCHEDULER", False)

    def _trace(self, msg: str):
        if not self._trace_enabled():
            return
        print(f"[cycle {self.sim.global_cycle:7d}] [SCHEDULER       ] {msg}")

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------
    def run(self, verbose=False, max_cycles=10_000_000):
        self._trace("run() start")

        while not self.is_done():
            if self.sim.global_cycle >= max_cycles:
                raise RuntimeError("Simulation exceeded max_cycles")

            self._issue_work()
            self.sim.step()
            self._tick_local_ops()
            self._handle_completions()

            if verbose and (self.sim.global_cycle % 5000 == 0):
                print(self.debug_status())

        self._trace(f"run() done | total_cycles={self.sim.global_cycle}")
        return self.sim.global_cycle

    def is_done(self) -> bool:
        return self.phase == "DONE"

    def debug_status(self) -> str:
        return (
            f"[cycle={self.sim.global_cycle}] "
            f"phase={self.phase} prep_stage={self.prep_stage} "
            f"ntt_ptr={self.ntt_ptr}/{len(self.ntt_plan)} "
            f"row_mac={self.row_mac_counts} "
            f"row_sub={self.row_sub_done} "
            f"completed_w={self.completed_w_rows}/{self.cfg.DILITHIUM_K} "
            f"packed_rows={self.packed_rows}/{self.cfg.DILITHIUM_K} "
            f"a_next={self.next_a_index}/{self.total_a_polys} "
            f"final_hash_issued={self.final_hash_issued} "
            f"final_hash_done={self.final_hash_done} "
            f"compare_done={self.compare_done}"
        )

    # ------------------------------------------------------------------
    # NTT plan
    # ------------------------------------------------------------------
    def _build_ntt_plan(self):
        plan = []

        # Row 0
        plan.extend([
            {"op": "fwd", "src_kind": "z",  "poly": 0, "dst": "z_ntt"},
            {"op": "fwd", "src_kind": "c",  "poly": None, "dst": "c_ntt"},
            {"op": "fwd", "src_kind": "z",  "poly": 1, "dst": "z_ntt"},
            {"op": "fwd", "src_kind": "t1", "poly": 0, "dst": "t1_ntt"},
            {"op": "fwd", "src_kind": "z",  "poly": 2, "dst": "z_ntt"},
            {"op": "fwd", "src_kind": "z",  "poly": 3, "dst": "z_ntt"},
        ])

        # Row 1..K-1
        for row in range(1, self.cfg.DILITHIUM_K):
            plan.extend([
                {"op": "fwd", "src_kind": "z",  "poly": 0, "dst": "z_ntt"},
                {"op": "inv", "src_kind": "w",  "row": row - 1, "dst": "w_final"},
                {"op": "fwd", "src_kind": "z",  "poly": 1, "dst": "z_ntt"},
                {"op": "fwd", "src_kind": "t1", "poly": row, "dst": "t1_ntt"},
                {"op": "fwd", "src_kind": "z",  "poly": 2, "dst": "z_ntt"},
                {"op": "fwd", "src_kind": "z",  "poly": 3, "dst": "z_ntt"},
            ])

        # Final inverse NTT
        plan.append({"op": "inv", "src_kind": "w", "row": self.cfg.DILITHIUM_K - 1, "dst": "w_final"})
        return plan

    # ------------------------------------------------------------------
    # Issue dispatch
    # ------------------------------------------------------------------
    def _issue_work(self):
        if self.phase == "PREP":
            self._issue_prep()
            return

        if self.phase == "MAIN":
            self._issue_a_generation()
            self._issue_ntt()
            self._issue_pau()
            self._issue_postprocess()
            self._issue_final_hash()
            self._maybe_start_compare()
            return

    # ------------------------------------------------------------------
    # PREP
    # ------------------------------------------------------------------
    def _issue_prep(self):
        if self.prep_stage == "UNPACK":
            if not self.prep_issued:
                self.sim.pk_unpacker.start_unpack(self.sim.memory.get_region_bytes("pk"))
                self.sim.sig_unpacker.start_unpack(self.sim.memory.get_region_bytes("signature"))
                self.prep_issued = True
                self._trace("issue PREP/UNPACK | pk_unpack + sig_unpack")
            return

        if self.prep_stage == "CHALLENGE_C":
            if not self.prep_issued:
                tag = "challenge_c"
                self.sim.shake.start_hash(
                    mode=256,
                    input_bytes=self.cfg.SEED_BYTES,
                    squeeze_blocks=1,
                    tag=tag,
                )
                self.sim.sample_in_ball.start_sampling(
                    seed=b"challenge_c_seed",
                    tag=tag,
                    stream_mode="shake256",
                )
                self.challenge_pair_active = True
                self.prep_issued = True
                self._trace("issue PREP/CHALLENGE_C | SHAKE256 + SampleInBall")
            return

        if self.prep_stage == "TR":
            if not self.prep_issued:
                self.sim.shake.start_hash(
                    mode=256,
                    input_bytes=self.sim.memory.get_region_bytes("pk"),
                    squeeze_blocks=1,
                    tag="tr",
                )
                self.prep_issued = True
                self._trace(f"issue PREP/TR | SHAKE256(pk) input_bytes={self.sim.memory.get_region_bytes('pk')}")
            return

        if self.prep_stage == "MU":
            if not self.prep_issued:
                input_bytes = self.cfg.CRH_BYTES + self.sim.memory.get_region_bytes("message")
                self.sim.shake.start_hash(
                    mode=256,
                    input_bytes=input_bytes,
                    squeeze_blocks=1,
                    tag="mu",
                )
                self.prep_issued = True
                self._trace(f"issue PREP/MU | SHAKE256(tr||msg) input_bytes={input_bytes}")
            return

    # ------------------------------------------------------------------
    # A generation
    # ------------------------------------------------------------------
    def _issue_a_generation(self):
        if self.a_pair_active:
            return
        if self.next_a_index >= self.total_a_polys:
            return
        if self.sim.shake.busy:
            return
        if self.sim.matrix_a_sampler.busy:
            return
        if not self.buffers["A_elem"].empty:
            return

        row = self.next_a_index // self.cfg.DILITHIUM_L
        col = self.next_a_index % self.cfg.DILITHIUM_L
        tag = {"row": row, "col": col}

        self.sim.shake.start_hash(
            mode=128,
            input_bytes=self.cfg.A_EXPAND_INPUT_BYTES,
            squeeze_blocks=self.cfg.A_EXPAND_BLOCKS_PER_POLY,
            tag=tag,
        )
        self.sim.matrix_a_sampler.start_sampling(
            seed=f"A|{row}|{col}".encode(),
            tag=tag,
            stream_mode="shake128",
        )

        self.a_pair_active = True
        self.a_inflight_tag = tag
        self.next_a_index += 1
        self._trace(f"issue A generation | row={row} col={col} squeeze_blocks={self.cfg.A_EXPAND_BLOCKS_PER_POLY}")

    # ------------------------------------------------------------------
    # NTT issue
    # ------------------------------------------------------------------
    def _issue_ntt(self):
        if self.sim.ntt.busy:
            return
        if self.ntt_ptr >= len(self.ntt_plan):
            return

        task = self.ntt_plan[self.ntt_ptr]

        if task["op"] == "fwd":
            dst = task["dst"]
            if not self.buffers[dst].empty:
                return

            if task["src_kind"] == "c" and not self.c_ready:
                return

            tag = {
                "op": "fwd",
                "src_kind": task["src_kind"],
                "poly": task.get("poly"),
                "dst": dst,
            }
            self.sim.ntt.start_transform(is_intt=False, tag=tag)
            self._trace(f"issue NTT/FWD | src={task['src_kind']} poly={task.get('poly')} dst={dst}")
            return

        if task["op"] == "inv":
            if not self.buffers["w_final"].empty:
                return
            if not self.buffers["w_ntt"].full:
                return

            payload = self.buffers["w_ntt"].peek()
            if payload["kind"] != "w_ntt_full":
                return
            if payload["row"] != task["row"]:
                return

            self.buffers["w_ntt"].pop()

            tag = {
                "op": "inv",
                "src_kind": "w",
                "row": task["row"],
                "dst": "w_final",
            }
            self.sim.ntt.start_transform(is_intt=True, tag=tag)
            self._trace(f"issue NTT/INTT | row={task['row']}")
            return

    # ------------------------------------------------------------------
    # PAU issue
    # ------------------------------------------------------------------
    def _issue_pau(self):
        if self.sim.pau.busy:
            return

        row = self._current_pau_row()
        if row is None:
            return

        mac_count = self.row_mac_counts[row]

        if mac_count == 0:
            if self._can_start_mac_first(row):
                self.buffers["A_elem"].pop()
                self.buffers["z_ntt"].pop()
                self.sim.pau.start_job(op="mac_add_first", row=row, col=0)
                self._trace(f"issue PAU/mac_add_first | row={row} col=0")
            return

        if 0 < mac_count < self.cfg.DILITHIUM_L:
            if self._can_start_mac_acc(row, mac_count):
                self.buffers["A_elem"].pop()
                self.buffers["z_ntt"].pop()
                self.buffers["w_ntt"].pop()
                self.sim.pau.start_job(op="mac_add_acc", row=row, col=mac_count)
                self._trace(f"issue PAU/mac_add_acc | row={row} col={mac_count}")
            return

        if mac_count == self.cfg.DILITHIUM_L:
            if self._can_start_mac_sub(row):
                self.buffers["t1_ntt"].pop()
                self.buffers["w_ntt"].pop()
                self.sim.pau.start_job(op="mac_sub", row=row)
                self._trace(f"issue PAU/mac_sub | row={row}")
            return

    def _current_pau_row(self):
        for row in range(self.cfg.DILITHIUM_K):
            if not self.row_sub_done[row]:
                return row
        return None

    def _can_start_mac_first(self, row: int) -> bool:
        if not self.buffers["A_elem"].full:
            return False
        if not self.buffers["z_ntt"].full:
            return False

        a = self.buffers["A_elem"].peek()
        z = self.buffers["z_ntt"].peek()

        return (
            a["kind"] == "A_elem"
            and a["row"] == row
            and a["col"] == 0
            and z["kind"] == "z_ntt"
            and z["poly"] == 0
        )

    def _can_start_mac_acc(self, row: int, expected_col: int) -> bool:
        if not self.buffers["A_elem"].full:
            return False
        if not self.buffers["z_ntt"].full:
            return False
        if not self.buffers["w_ntt"].full:
            return False

        a = self.buffers["A_elem"].peek()
        z = self.buffers["z_ntt"].peek()
        w = self.buffers["w_ntt"].peek()

        return (
            a["kind"] == "A_elem"
            and a["row"] == row
            and a["col"] == expected_col
            and z["kind"] == "z_ntt"
            and z["poly"] == expected_col
            and w["kind"] == "w_ntt_partial"
            and w["row"] == row
            and w["accum_count"] == expected_col
        )

    def _can_start_mac_sub(self, row: int) -> bool:
        if not self.buffers["c_ntt"].full:
            return False
        if not self.buffers["t1_ntt"].full:
            return False
        if not self.buffers["w_ntt"].full:
            return False

        c = self.buffers["c_ntt"].peek()
        t1 = self.buffers["t1_ntt"].peek()
        w = self.buffers["w_ntt"].peek()

        return (
            c["kind"] == "c_ntt"
            and t1["kind"] == "t1_ntt"
            and t1["row"] == row
            and w["kind"] == "w_ntt_partial"
            and w["row"] == row
            and w["accum_count"] == self.cfg.DILITHIUM_L
        )

    # ------------------------------------------------------------------
    # Postprocess: use_hint + pack
    # ------------------------------------------------------------------
    def _issue_postprocess(self):
        if self.sim.hint.busy:
            return
        if not self.post_queue:
            return

        row = self.post_queue.pop(0)
        self.sim.hint.start_job(row=row, tag={"row": row})
        self._trace(f"issue POST/use_hint+pack | row={row}")

    # ------------------------------------------------------------------
    # Final hash
    # ------------------------------------------------------------------
    def _issue_final_hash(self):
        if self.final_hash_issued:
            return
        if self.sim.shake.busy:
            return

        # SHAKE becomes available immediately after A generation finishes
        if self.next_a_index < self.total_a_polys:
            return
        if self.a_pair_active:
            return

        # Need mu ready before final hash can begin
        if not self.mu_ready:
            return

        # Need all NTT/PAU work logically issued so final w-path is underway
        if self.ntt_ptr < len(self.ntt_plan):
            return
        if not all(self.row_sub_done):
            return

        # Streaming-absorb timing approximation:
        # Start final SHAKE as soon as SHAKE is free after A generation,
        # without waiting for all packed rows to be ready.
        # Input size is fixed by Dilithium2 standard:
        #   mu (CRH_BYTES) + packed_w1 (K * 192B)
        input_bytes = getattr(
            self.cfg,
            "FINAL_HASH_INPUT_BYTES",
            self.cfg.CRH_BYTES + self.cfg.DILITHIUM_K * self.cfg.W1_PACKED_BYTES_PER_POLY,
        )

        self.sim.shake.start_hash(
            mode=256,
            input_bytes=input_bytes,
            squeeze_blocks=1,
            tag="c_prime",
        )
        self.final_hash_issued = True
        self._trace(
            f"issue FINAL_HASH | SHAKE256(mu||packed_w1) input_bytes={input_bytes} "
            f"(streaming-absorb approximation)"
        )

    def _maybe_start_compare(self):
        if self.compare_active or self.compare_done:
            return

        # Compare may start only after:
        #   1) final hash finished
        #   2) all packed rows finished
        if not self.final_hash_done:
            return
        if self.packed_rows < self.cfg.DILITHIUM_K:
            return

        self.compare_active = True
        self.compare_cycles_left = math.ceil(
            (self.cfg.FINAL_CHALLENGE_BYTES * 8) / self.cfg.MEM_BANDWIDTH
        )
        self._trace(f"start compare | cycles={self.compare_cycles_left}")

    # ------------------------------------------------------------------
    # Local non-module ops
    # ------------------------------------------------------------------
    def _tick_local_ops(self):
        if not self.compare_active:
            return

        self.compare_cycles_left -= 1
        if self.compare_cycles_left <= 0:
            self.compare_active = False
            self.compare_done = True
            self.verify_pass = True  # timing-only model
            self.phase = "DONE"
            self._trace("compare done | verify_pass=True | phase -> DONE")

    # ------------------------------------------------------------------
    # Completion handling
    # ------------------------------------------------------------------
    def _handle_completions(self):
        self._handle_unpack_completion()
        self._handle_challenge_completion()
        self._handle_hash_completion()
        self._handle_a_pair_completion()
        self._handle_ntt_completion()
        self._handle_pau_completion()
        self._retire_w_final()
        self._handle_hint_completion()
        self._handle_final_hash_completion()
        self._maybe_start_compare()

    def _handle_unpack_completion(self):
        if self.phase != "PREP":
            return

        if self.prep_stage == "UNPACK":
            if (not self.sim.pk_unpacker.busy) and (not self.sim.sig_unpacker.busy):
                self.prep_stage = "CHALLENGE_C"
                self.prep_issued = False
                self._trace("complete PREP/UNPACK | next -> CHALLENGE_C")

    def _handle_challenge_completion(self):
        if self.phase != "PREP":
            return
        if self.prep_stage != "CHALLENGE_C":
            return
        if not self.challenge_pair_active:
            return

        if (not self.sim.shake.busy) and (not self.sim.sample_in_ball.busy):
            self.c_ready = True
            self.challenge_pair_active = False
            self.prep_stage = "TR"
            self.prep_issued = False
            self._trace("complete PREP/CHALLENGE_C | c_ready=True | next -> TR")

    def _handle_hash_completion(self):
        if self.phase != "PREP":
            return

        if self.prep_stage == "TR" and self.prep_issued:
            if not self.sim.shake.busy:
                self.tr_ready = True
                self.prep_stage = "MU"
                self.prep_issued = False
                self._trace("complete PREP/TR | tr_ready=True | next -> MU")
                return

        if self.prep_stage == "MU" and self.prep_issued:
            if not self.sim.shake.busy:
                self.mu_ready = True
                self.prep_stage = "DONE"
                self.prep_issued = False
                self.phase = "MAIN"
                self._trace("complete PREP/MU | mu_ready=True | phase -> MAIN")
                return

    def _handle_a_pair_completion(self):
        if self.phase != "MAIN":
            return
        if not self.a_pair_active:
            return

        if (not self.sim.shake.busy) and (not self.sim.matrix_a_sampler.busy):
            if self.a_inflight_tag is None:
                raise RuntimeError("A pair completed without inflight tag")

            if not self.buffers["A_elem"].empty:
                raise RuntimeError("A_elem buffer should be empty when committing new A polynomial")

            self.buffers["A_elem"].push({
                "kind": "A_elem",
                "row": self.a_inflight_tag["row"],
                "col": self.a_inflight_tag["col"],
            })

            self._trace(
                f"complete A generation | row={self.a_inflight_tag['row']} "
                f"col={self.a_inflight_tag['col']} -> A_elem buffer"
            )

            self.a_pair_active = False
            self.a_inflight_tag = None

    def _handle_ntt_completion(self):
        if not self.sim.ntt.done_pulse:
            return

        tag = self.sim.ntt.current_job["tag"]
        if tag is None:
            raise RuntimeError("NTT done without tag")

        if tag["op"] == "fwd":
            if tag["src_kind"] == "z":
                self.buffers["z_ntt"].push({
                    "kind": "z_ntt",
                    "poly": tag["poly"],
                })
            elif tag["src_kind"] == "c":
                self.buffers["c_ntt"].push({
                    "kind": "c_ntt",
                })
            elif tag["src_kind"] == "t1":
                self.buffers["t1_ntt"].push({
                    "kind": "t1_ntt",
                    "row": tag["poly"],
                })
            else:
                raise RuntimeError(f"Unexpected forward NTT src_kind: {tag['src_kind']}")

            self.ntt_ptr += 1
            self._trace(f"complete NTT/FWD | src={tag['src_kind']} poly={tag.get('poly')} -> {tag['dst']}")
            return

        if tag["op"] == "inv":
            self.buffers["w_final"].push({
                "kind": "w_final",
                "row": tag["row"],
            })
            self.ntt_ptr += 1
            self._trace(f"complete NTT/INTT | row={tag['row']} -> w_final")
            return

    def _handle_pau_completion(self):
        if not self.sim.pau.done_pulse:
            return

        job = self.sim.pau.current_job
        if job is None:
            raise RuntimeError("PAU completed without current_job")

        op = job["op"]
        row = job["row"]

        if op == "mac_add_first":
            self.row_mac_counts[row] = 1
            self.buffers["w_ntt"].push({
                "kind": "w_ntt_partial",
                "row": row,
                "accum_count": 1,
            })
            self._trace(f"complete PAU/mac_add_first | row={row} accum_count=1")
            return

        if op == "mac_add_acc":
            self.row_mac_counts[row] += 1
            self.buffers["w_ntt"].push({
                "kind": "w_ntt_partial",
                "row": row,
                "accum_count": self.row_mac_counts[row],
            })
            self._trace(f"complete PAU/mac_add_acc | row={row} accum_count={self.row_mac_counts[row]}")
            return

        if op == "mac_sub":
            self.row_sub_done[row] = True
            self.buffers["w_ntt"].push({
                "kind": "w_ntt_full",
                "row": row,
            })
            self._trace(f"complete PAU/mac_sub | row={row} -> w_ntt_full")
            return

    def _retire_w_final(self):
        if not self.buffers["w_final"].full:
            return

        payload = self.buffers["w_final"].pop()
        if payload["kind"] != "w_final":
            raise RuntimeError("Invalid payload in w_final buffer")

        self.completed_w_rows += 1
        self.post_queue.append(payload["row"])
        self._trace(f"retire w_final | row={payload['row']} | completed_w_rows={self.completed_w_rows}")

    def _handle_hint_completion(self):
        if not self.sim.hint.done_pulse:
            return

        job = self.sim.hint.current_job
        if job is None:
            raise RuntimeError("HintPack completed without current_job")

        self.packed_rows += 1
        self.packed_w1_bytes += self.cfg.W1_PACKED_BYTES_PER_POLY
        self._trace(
            f"complete POST/use_hint+pack | row={job['row']} | "
            f"packed_rows={self.packed_rows} packed_w1_bytes={self.packed_w1_bytes}"
        )

    def _handle_final_hash_completion(self):
        if not self.final_hash_issued:
            return
        if self.final_hash_done:
            return

        if self.sim.shake.done_pulse and self.sim.shake.current_job is not None:
            tag = self.sim.shake.current_job["tag"]
            if tag == "c_prime":
                self.final_hash_done = True
                self._trace("complete FINAL_HASH | c_prime ready")