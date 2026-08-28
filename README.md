# VDF — Verifiable Delay Function timelock for Starknet (Cairo)

Wesolowski VDF verification + RSW timelock decryption, implemented as a provable
Cairo **executable** program (not a contract). Run the verification offchain,
prove it with the Stwo prover, and verify the proof onchain cheaply — the
Starknet-native pattern for "decryption capability materializes at a deadline"
with **no standing decryptor, no committee, no TEE**.

## Why

Sealed-bid auctions (and any "reveal at deadline" mechanism) need bids hidden
until a deadline with no trusted party holding the reveal key. This repo
provides the cryptographic primitive:

- **RSW timelock**: the encryptor (bidder) knows φ(N), so they derive the
  decryption key *instantly* (`y = x^(2^T mod φ(N)) mod N`). Everyone else must
  compute `y = x^(2^T) mod N` by **T sequential squarings** — the delay. The
  key materializes only at ~time T. No trusted setup: the bidder generates and
  discards the RSA factors.
- **Wesolowski VDF proof**: once someone has done the squarings, a short proof
  lets a verifier check correctness in **O(log T)** group ops:
  `y == π^L · x^(2^T mod L) (mod N)` with `L = H(x, y, T)`.

## Repository layout

```
cairo/
  lib/   # bigint + Wesolowski verifier (u64 limbs, u256 accumulation, Barrett)
  exec/  # #[executable] vdf_verify entrypoint, depends on lib
ref/     # Python reference implementation + exact Cairo-algorithm model
vectors/ # test vectors (RSW keys + Wesolowski proofs)
scripts/ # generators: vectors, Cairo tests, executable args
skill/   # the Hermes skill for this work (SKILL.md + references + scripts)
```

`skill/` is the Hermes Agent skill `vdf-timelock-cairo` — the operational playbook
for this exact pipeline (scheme, Cairo bigint pattern, scarb 2.20 executable
setup, proving gotchas), plus `references/whisper-integration-design.md`
capturing the sealed-bid auction design reasoning. Install it with
`hermes skills install` or copy `skill/SKILL.md` to your skills directory.

The Cairo `lib` and `exec` are **two standalone packages** (a scarb workspace
forces `[cairo]` settings at the workspace level, which conflicts with the
executable target's `enable-gas = false`).

## Documentation

The `docs/` directory is a [Vocs](https://vocs.dev) site (same stack as
Whisper's docs). Run it locally:

```sh
cd docs
pnpm install
pnpm dev          # local dev server
pnpm build        # static site output in docs/dist/
```

## Quick start

Requires scarb ≥ 2.20 (ships `scarb execute` / `scarb prove` / `scarb verify`).

```sh
# 1. Validate the bigint math (gas-cheap checks; both domains)
cd cairo/lib
scarb test                      # 2 passed, 1 ignored (full verify exceeds cairo-test gas cap)

# 2. Run the full Wesolowski verification as an executable (gas off)
cd ../exec
python3 ../../scripts/write_exec_512.py   # writes vectors/exec_args_512.json
scarb execute --arguments-file ../../vectors/exec_args_512.json --print-program-output
# Program output: 1   <- proof verifies

# 3. Prove the execution with Stwo (needs a big machine: 16GB+ RAM)
scarb execute --output=standard --arguments-file ../../vectors/exec_args_512.json
scarb prove --execution-id 1   # -> target/execute/vdf_exec/execution1/proof/proof.json
scarb verify target/execute/vdf_exec/execution1/proof/proof.json
```

The 1024-bit prover input is ~139MB and Stwo needs 10–17GB to prove it; the
512-bit default fits CI/small boxes. For production use a 2048-bit modulus
(`N_LIMBS = 32`) and a serious proving machine.

## How it works

### Cairo bigint (the non-obvious part)

Cairo `felt252` lacks `PartialOrd`, `Rem`, and shifts, and `/` is field
division — so bigint math uses:

- **u64 limbs** (little-endian), **u256 accumulation** for multiplication
  (products of two u64s fit comfortably; sums of ≤17 products < 2^133 fit u256)
- **u128 subtraction with borrow** (borrow applies to the subtrahend)
- **Barrett reduction** with `mu = floor(b^(2k)/N)` computed offchain (k+1 limbs)
- **Per-modulus limb domains**: N (512-bit → 8 limbs) and the 256-bit challenge
  L (4 limbs) each get their own Barrett constant

`ref/cairo_model_v2.py` is the exact Python mirror of the Cairo algorithm —
validate any change there first (it caught two real bugs: borrow direction and
mixed limb domains).

### Onchain verification (the end state)

The `exec/` package is a Cairo *program*; its execution is proven with Stwo and
verified with the Cairo recursive verifier (stwo-cairo ships one) — so a Starknet
tx never runs the ~4B-step computation, it just verifies a small proof.

## Status

- [x] Python reference + vectors (RSW + Wesolowski)
- [x] Cairo verifier (`lib`) + `#[executable]` entrypoint (`exec`)
- [x] `scarb execute` → output `1` on 256/512/1024-bit vectors
- [x] `scarb execute --output=standard` → prover input
- [ ] `scarb prove` (verified working on the pipeline; needs 16GB+ machine)
- [ ] Onchain recursive-verifier integration

## References

- STRK20 sealed-bid auction RFP: https://strk20.starknet.io/rfp/sealed-bid-auctions
- Stwo Cairo: https://github.com/starkware-libs/stwo-cairo (migrated to `starkware-libs/proving`)
- Scarb prove/verify: https://docs.swmansion.com/scarb/docs/extensions/prove-and-verify

License: Apache-2.0
