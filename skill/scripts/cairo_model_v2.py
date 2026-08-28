#!/usr/bin/env python3
"""Exact Python model of the Cairo bigint + Wesolowski verifier.

Validates the limb algorithm BEFORE porting to Cairo. Mirrors
lib/src/lib.cairo limb-for-limb: u64 limbs, u256 accumulation, Barrett
reduction, per-modulus limb domains.

Usage: python3 cairo_model_v2.py   (reads /tmp/vdf/vdf_vectors.json)
Change this file first when modifying the Cairo math; never port blind.
"""

import json

LIMB_BITS = 64
MASK = (1 << LIMB_BITS) - 1
TWO64 = 1 << LIMB_BITS


def to_limbs(v: int, n: int) -> list[int]:
    return [(v >> (LIMB_BITS * i)) & MASK for i in range(n)]


def from_limbs(limbs: list[int]) -> int:
    v = 0
    for i, limb in enumerate(limbs):
        v |= limb << (LIMB_BITS * i)
    return v


def bigint_mul(a: list[int], b: list[int], an: int, bn: int) -> list[int]:
    """Schoolbook product, output-limb-at-a-time with chained carry."""
    total = an + bn
    out = []
    carry = 0
    for t in range(total):
        acc = carry
        for i in range(an):
            j = t - i
            if 0 <= j < bn:
                acc += a[i] * b[j]
        out.append(acc & MASK)
        carry = acc >> LIMB_BITS
    return out


def sub_limbs(a: list[int], b: list[int], k: int) -> list[int]:
    """Limb-wise a - b with borrow. Borrow applies to the SUBTRAHEND."""
    out = []
    borrow = 0
    for i in range(k):
        minuend = a[i]
        subtrahend = b[i] + borrow
        if minuend >= subtrahend:
            out.append(minuend - subtrahend)
            borrow = 0
        else:
            out.append(minuend + TWO64 - subtrahend)
            borrow = 1
    return out


def ge_limbs(a: list[int], b: list[int], k: int) -> bool:
    for i in range(k - 1, -1, -1):
        if a[i] != b[i]:
            return a[i] > b[i]
    return True  # equal


def barrett_reduce(p: list[int], N: list[int], mu: list[int], k: int) -> list[int]:
    q1 = p[k - 1:]  # k+1 limbs
    q2 = bigint_mul(q1, mu, k + 1, k + 1)  # 2k+2 limbs
    q3 = q2[k + 1:]  # k+1 limbs
    q3n = bigint_mul(q3, N, k + 1, k)  # 2k+1 limbs

    r = []
    borrow = 0
    for i in range(k):
        minuend = p[i]
        subtrahend = q3n[i] + borrow
        if minuend >= subtrahend:
            r.append(minuend - subtrahend)
            borrow = 0
        else:
            r.append(minuend + TWO64 - subtrahend)
            borrow = 1

    for _ in range(2):  # normalize: at most 2 subtractions
        if ge_limbs(r, N, k):
            r = sub_limbs(r, N, k)
    return r


def modmul(a: list[int], b: list[int], N: list[int], mu: list[int], k: int) -> list[int]:
    return barrett_reduce(bigint_mul(a, b, k, k), N, mu, k)


def modpow(base, exp, exp_n, N, mu, k):
    one = [1] + [0] * (k - 1)
    result = barrett_reduce(bigint_mul(one, one, k, k), N, mu, k)
    base_red = modmul(base, one, N, mu, k)
    for i in range(exp_n):
        e = exp[i]
        for bit in range(LIMB_BITS):
            if (e >> bit) & 1:
                result = modmul(result, base_red, N, mu, k)
            base_red = modmul(base_red, base_red, N, mu, k)
    return result


def limbs_eq(a, b, k):
    return a[:k] == b[:k]


def barrett_mu(N_int: int, k: int) -> list[int]:
    return to_limbs((1 << (64 * 2 * k)) // N_int, k + 1)


def verify_vector(v: dict) -> bool:
    kN = v["n_limbs"]
    N = v["N_limbs"]
    x = v["x_limbs"]
    y = v["y_limbs"]
    pi = v["pi_limbs"]
    L = v["L_limbs"]
    r = v["r_limbs"]
    T = v["T"]
    N_int = int(v["N"], 16)
    L_int = int(v["L"], 16)
    kL = 4

    muN = barrett_mu(N_int, kN)
    muL = barrett_mu(L_int, kL)
    L_domain = to_limbs(L_int, kL)

    r_calc = modpow(to_limbs(2, kL), to_limbs(T, 2), 2, L_domain, muL, kL)
    assert from_limbs(r_calc) == int(v["r"], 16), f"r mismatch: {from_limbs(r_calc):x}"

    piL = modpow(pi, L, kL, N, muN, kN)
    xr = modpow(x, r, kL, N, muN, kN)
    lhs = modmul(piL, xr, N, muN, kN)
    return from_limbs(lhs) == int(v["y"], 16)


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/vdf/vdf_vectors.json"
    vectors = json.load(open(path))
    for v in vectors:
        print(f"{v['name']}: {'PASS' if verify_vector(v) else 'FAIL'}")
