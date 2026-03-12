import os
import sys
import random
from dataclasses import dataclass, asdict

# Add project root to import path
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
MODULES_DIR = os.path.dirname(THIS_DIR)
ROOT_DIR = os.path.dirname(MODULES_DIR)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import config
from modules.shake import ShakeModule
from modules.sampler import UniformSamplerModule


@dataclass
class BlockResult:
    block_idx: int
    absorb_cycles: int
    permute_cycles: int
    squeeze_cycles: int
    sampler_active_cycles_in_block: int
    accepted_coeffs_after_block: int
    sampler_done_after_block: bool


@dataclass
class PolyResult:
    poly_idx: int
    blocks: list
    total_absorb_cycles: int
    total_permute_cycles: int
    total_squeeze_cycles: int
    total_sampler_active_cycles: int
    total_cycles_with_sampling_overlap: int
    accepted_coeffs: int
    sampler_done: bool


class MatrixAGenerationTester:
    """
    Test model for Matrix A polynomial generation using the *current* codebase.

    Current modeling assumption:
      - One A polynomial is produced by 5 SHAKE128 blocks.
      - Each block runs: ABSORB -> PERMUTE -> SQUEEZE.
      - UniformSampler overlaps with SQUEEZE only.
      - Therefore polynomial total latency is:
            sum(absorb + permute + squeeze) over 5 blocks
        and sampler latency is reported separately as active squeeze cycles.
    """

    def __init__(self, cfg, seed: int = 1234):
        self.cfg = cfg
        self.seed = seed

    def _run_until_idle(self, module):
        start_cycles = getattr(module, "cycle_count", 0)
        while module.state != "IDLE":
            module.tick()
        end_cycles = getattr(module, "cycle_count", 0)
        return end_cycles - start_cycles

    def _run_squeeze_with_sampler(self, shake: ShakeModule, sampler: UniformSamplerModule):
        """
        Run one SQUEEZE phase and overlap sampler progress in the same cycles.
        Returns:
            squeeze_cycles,
            sampler_active_cycles_in_this_block
        """
        start_cycles = shake.cycle_count
        active_cycles = 0
        while shake.state != "IDLE":
            # For the current codebase, sampler should only advance during SQUEEZE.
            # Since this loop is only called after start_squeeze(), every cycle here
            # is a valid squeeze-stream cycle.
            shake.tick()
            if not sampler.is_done:
                sampler.tick(shake_is_squeezing=True)
                active_cycles += 1

        return shake.cycle_count - start_cycles, active_cycles

    def run_one_a_poly(self, poly_idx: int = 0) -> PolyResult:
        random.seed(self.seed + poly_idx)

        shake = ShakeModule(self.cfg)
        sampler = UniformSamplerModule(self.cfg)
        sampler.reset()

        block_results = []
        total_absorb = 0
        total_permute = 0
        total_squeeze = 0
        total_sampler_active = 0

        for block_idx in range(5):
            # 1) Absorb
            shake.start_absorb(mode=128, input_bytes=34)
            absorb_cycles = self._run_until_idle(shake)
            total_absorb += absorb_cycles

            # 2) Permute
            shake.start_permute()
            permute_cycles = self._run_until_idle(shake)
            total_permute += permute_cycles

            # 3) Squeeze + overlapped sampling
            shake.start_squeeze(mode=128)
            squeeze_cycles, sampler_active_cycles = self._run_squeeze_with_sampler(shake, sampler)
            total_squeeze += squeeze_cycles
            total_sampler_active += sampler_active_cycles

            block_results.append(
                BlockResult(
                    block_idx=block_idx,
                    absorb_cycles=absorb_cycles,
                    permute_cycles=permute_cycles,
                    squeeze_cycles=squeeze_cycles,
                    sampler_active_cycles_in_block=sampler_active_cycles,
                    accepted_coeffs_after_block=sampler.accepted_coeffs,
                    sampler_done_after_block=sampler.is_done,
                )
            )

        total_cycles = total_absorb + total_permute + total_squeeze

        return PolyResult(
            poly_idx=poly_idx,
            blocks=block_results,
            total_absorb_cycles=total_absorb,
            total_permute_cycles=total_permute,
            total_squeeze_cycles=total_squeeze,
            total_sampler_active_cycles=total_sampler_active,
            total_cycles_with_sampling_overlap=total_cycles,
            accepted_coeffs=sampler.accepted_coeffs,
            sampler_done=sampler.is_done,
        )

    def run_full_matrix_a(self):
        poly_results = []
        total_cycles = 0
        total_sampler_active_cycles = 0

        num_polys = self.cfg.DILITHIUM_K * self.cfg.DILITHIUM_L
        for poly_idx in range(num_polys):
            result = self.run_one_a_poly(poly_idx=poly_idx)
            poly_results.append(result)
            total_cycles += result.total_cycles_with_sampling_overlap
            total_sampler_active_cycles += result.total_sampler_active_cycles

        return {
            "num_polynomials": num_polys,
            "matrix_shape": (self.cfg.DILITHIUM_K, self.cfg.DILITHIUM_L),
            "poly_results": poly_results,
            "total_cycles_with_sampling_overlap": total_cycles,
            "total_sampler_active_cycles": total_sampler_active_cycles,
        }


def print_one_poly_report(poly_result: PolyResult):
    print("=" * 72)
    print(f"[A Polynomial #{poly_result.poly_idx}]")
    print("=" * 72)
    print("Per-block phase cycles:")
    for blk in poly_result.blocks:
        print(
            f"  Block {blk.block_idx}: "
            f"Absorb={blk.absorb_cycles:3d}, "
            f"Permute={blk.permute_cycles:3d}, "
            f"Squeeze={blk.squeeze_cycles:3d}, "
            f"Sampler-active={blk.sampler_active_cycles_in_block:3d}, "
            f"Accepted={blk.accepted_coeffs_after_block:3d}, "
            f"Done={blk.sampler_done_after_block}"
        )

    print("\nSummary:")
    print(f"  Total Absorb cycles               : {poly_result.total_absorb_cycles}")
    print(f"  Total Permute cycles              : {poly_result.total_permute_cycles}")
    print(f"  Total Squeeze cycles              : {poly_result.total_squeeze_cycles}")
    print(f"  Total Sampler active cycles       : {poly_result.total_sampler_active_cycles}")
    print(f"  Total poly cycles (with overlap)  : {poly_result.total_cycles_with_sampling_overlap}")
    print(f"  Accepted coeffs                   : {poly_result.accepted_coeffs}")
    print(f"  Sampler done within 5 blocks      : {poly_result.sampler_done}")


def print_full_matrix_report(matrix_result):
    print("=" * 72)
    print("[Full Matrix A Generation]")
    print("=" * 72)
    print(f"Matrix shape                        : {matrix_result['matrix_shape'][0]} x {matrix_result['matrix_shape'][1]}")
    print(f"Number of polynomials               : {matrix_result['num_polynomials']}")
    print(f"Total sampler active cycles         : {matrix_result['total_sampler_active_cycles']}")
    print(f"Total matrix-A cycles (with overlap): {matrix_result['total_cycles_with_sampling_overlap']}")

    print("\nPer-polynomial totals:")
    for poly in matrix_result["poly_results"]:
        print(
            f"  Poly {poly.poly_idx:2d}: "
            f"Absorb={poly.total_absorb_cycles:4d}, "
            f"Permute={poly.total_permute_cycles:4d}, "
            f"Squeeze={poly.total_squeeze_cycles:4d}, "
            f"Sampler-active={poly.total_sampler_active_cycles:4d}, "
            f"Total={poly.total_cycles_with_sampling_overlap:4d}, "
            f"Accepted={poly.accepted_coeffs:3d}, "
            f"Done={poly.sampler_done}"
        )


if __name__ == "__main__":
    tester = MatrixAGenerationTester(config, seed=1234)

    # 1) One A polynomial: show Absorb/Permute/Squeeze cycles block-by-block,
    #    and total including sampling overlap.
    one_poly = tester.run_one_a_poly(poly_idx=0)
    print_one_poly_report(one_poly)

    print()

    # 2) Full Matrix A = K x L polynomials.
    full_matrix = tester.run_full_matrix_a()
    print_full_matrix_report(full_matrix)
