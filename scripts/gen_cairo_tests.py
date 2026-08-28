#!/usr/bin/env python3
"""Generate Cairo test file (u64 limbs) + executable input args from vectors."""

import json

VECTORS = json.load(open("/tmp/vdf/vdf_vectors.json"))


def limbs_cairo(limbs: list[int]) -> str:
    inner = ", ".join(f"{x}" for x in limbs)
    return f"array![{inner}].span()"


def barrett_mu(N_int: int, k: int) -> list[int]:
    b = 1 << 64
    n = k + 1
    mask = (1 << 64) - 1
    mu = (b ** (2 * k)) // N_int
    return [(mu >> (64 * i)) & mask for i in range(n)]


def gen_tests():
    print("use vdf::{verify_vdf, N_LIMBS, L_LIMBS};")
    print()
    print("#[cfg(test)]")
    print("mod tests {")
    print("    use super::*;")
    print()
    for v in VECTORS:
        name = v["name"]
        N_int = int(v["N"], 16)
        L_int = int(v["L"], 16)
        muN = barrett_mu(N_int, v["n_limbs"])
        muL = barrett_mu(L_int, 4)
        T = v["T"]
        T_limbs = [T & ((1 << 64) - 1), (T >> 64) & ((1 << 64) - 1)]

        print(f"    #[test]")
        print(f"    fn {name}_wesolowski_verifies() {{")
        print(f"        let N = {limbs_cairo(v['N_limbs'])};")
        print(f"        let mu_n = {limbs_cairo(muN)};")
        print(f"        let x = {limbs_cairo(v['x_limbs'])};")
        print(f"        let y = {limbs_cairo(v['y_limbs'])};")
        print(f"        let pi = {limbs_cairo(v['pi_limbs'])};")
        print(f"        let L = {limbs_cairo(v['L_limbs'][:4])};")
        print(f"        let mu_l = {limbs_cairo(muL)};")
        print(f"        let r = {limbs_cairo(v['r_limbs'][:4])};")
        print(f"        let T_limbs = {limbs_cairo(T_limbs)};")
        print(
            f"        assert(verify_vdf(N, mu_n, x, y, pi, L, mu_l, r, T_limbs, 2), 'VDF must verify');"
        )
        print("    }")
        print()
    print("}")


def gen_exec_args():
    """Flat felt252 input for the #[executable] entrypoint (one vector)."""
    v = VECTORS[0]
    N_int = int(v["N"], 16)
    L_int = int(v["L"], 16)
    muN = barrett_mu(N_int, v["n_limbs"])
    muL = barrett_mu(L_int, 4)
    T = v["T"]
    T_limbs = [T & ((1 << 64) - 1), (T >> 64) & ((1 << 64) - 1)]
    flat = (
        v["N_limbs"]
        + muN
        + v["x_limbs"]
        + v["y_limbs"]
        + v["pi_limbs"]
        + v["L_limbs"][:4]
        + muL
        + v["r_limbs"][:4]
        + T_limbs
    )
    # JSON array of decimal strings (felt252 serde for executables)
    print(json.dumps([str(x) for x in flat]))


if __name__ == "__main__":
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "tests"
    if mode == "tests":
        gen_tests()
    elif mode == "args":
        gen_exec_args()
