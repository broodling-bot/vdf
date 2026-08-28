#!/usr/bin/env python3
"""RSW timelock + Wesolowski VDF reference: solves, proves, verifies, and
generates JSON test vectors consumed by the Cairo verifier tests / exec args.

Usage: python3 vdf_reference.py [output.json]
"""
import hashlib
import json
import secrets
import sys


def sha256_int(*values: int) -> int:
    h = hashlib.sha256()
    for v in values:
        h.update(v.to_bytes((v.bit_length() + 7) // 8 or 1, "big"))
    return int.from_bytes(h.digest(), "big")


def sequential_square(x: int, T: int, N: int) -> int:
    y = x
    for _ in range(T):
        y = (y * y) % N
    return y


def wesolowski_prove(N: int, T: int, x: int, y: int) -> tuple:
    L = sha256_int(x, y, T)
    q, r = divmod(1 << T, L)
    pi = pow(x, q, N)
    return pi, L, r


def wesolowski_verify(N: int, T: int, x: int, y: int, pi: int) -> bool:
    L = sha256_int(x, y, T)
    r = pow(2, T, L)
    return (pow(pi, L, N) * pow(x, r, N)) % N == y


def limbify(value: int, limb_bits: int, n_limbs: int) -> list[int]:
    mask = (1 << limb_bits) - 1
    return [(value >> (limb_bits * i)) & mask for i in range(n_limbs)]


def is_probable_prime(n: int, rounds: int = 16) -> bool:
    if n < 2:
        return False
    for p in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if n % p == 0:
            return n == p
    d, s = n - 1, 0
    while d % 2 == 0:
        s += 1
        d //= 2
    for _ in range(rounds):
        a = secrets.randbelow(n - 3) + 2
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(s - 1):
            x = (x * x) % n
            if x == n - 1:
                break
        else:
            return False
    return True


def make_vector(n_bits: int, T: int, limb_bits: int = 64, seed: int | None = None) -> dict:
    rng = __import__("random").Random(seed) if seed is not None else secrets.SystemRandom()

    def probable_prime(bits: int):
        while True:
            p = rng.getrandbits(bits) | (1 << (bits - 1)) | 1
            if is_probable_prime(p):
                return p

    p = probable_prime(n_bits // 2)
    q = probable_prime(n_bits // 2)
    N = p * q
    phi = (p - 1) * (q - 1)

    x = rng.getrandbits(n_bits - 8) | 1
    x %= N
    if x == 0:
        x = 1

    # RSW shortcut: encryptor knows phi(N).
    y_fast = pow(x, pow(2, T, phi), N)
    assert y_fast == sequential_square(x, T, N), "RSW shortcut must match sequential squaring"

    pi, L, r = wesolowski_prove(N, T, x, y_fast)
    assert wesolowski_verify(N, T, x, y_fast, pi), "proof must verify"

    n_limbs = (n_bits + limb_bits - 1) // limb_bits
    return {
        "name": f"rsa{n_bits}_T{T}",
        "n_bits": n_bits,
        "limb_bits": limb_bits,
        "n_limbs": n_limbs,
        "T": T,
        "N": hex(N),
        "N_limbs": limbify(N, limb_bits, n_limbs),
        "x": hex(x),
        "x_limbs": limbify(x, limb_bits, n_limbs),
        "y": hex(y_fast),
        "y_limbs": limbify(y_fast, limb_bits, n_limbs),
        "pi": hex(pi),
        "pi_limbs": limbify(pi, limb_bits, n_limbs),
        "L": hex(L),
        "L_limbs": limbify(L, limb_bits, n_limbs),
        "r": hex(r),
        "r_limbs": limbify(r, limb_bits, n_limbs),
    }


if __name__ == "__main__":
    out_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/vdf/vdf_vectors.json"
    vectors = [
        make_vector(1024, T=1 << 20, seed=42),  # meaningful Wesolowski proof
        make_vector(512, T=1 << 16, seed=99),  # small modulus for CI/OOM-constrained boxes
    ]
    with open(out_path, "w") as f:
        json.dump(vectors, f, indent=2)
    for v in vectors:
        print(f"{v['name']}: L-bits={int(v['L'], 16).bit_length()} pi-bits={int(v['pi'], 16).bit_length()}")
    print(f"wrote {out_path}")
