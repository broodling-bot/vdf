---
name: vdf-timelock-cairo
description: Implement VDF (Verifiable Delay Function) timelock decryption and deadline-decryption mechanisms on Starknet — Wesolowski VDF verification in Cairo, RSW timelock encryption, and the scarb 2.20 executable + Stwo proving pipeline (scarb execute → scarb prove → scarb verify). Use when building "decrypt at deadline" primitives, sealed-bid auction reveals, or any Cairo program that must be proven offchain and verified onchain. Covers the validated u64/u256 bigint pattern for Cairo 2.20 (felt252 lacks PartialOrd/Rem/shifts), Barrett reduction, and the exact toolchain gotchas (gas caps, OOM, arg formats).
tags: [cairo, starknet, vdf, timelock, wesolowski, rsw, stwo, proving, cryptography]
related_skills: [strk20-privacy-integration, ocr-and-documents]
---

# VDF Timelock Decryption on Starknet (Cairo executable + Stwo proof)

## When to use

- Sealed-bid auctions where bid amounts must stay hidden **until a deadline** with **no standing decryptor** (no single operator holding the reveal key).
- Any "decryption capability materializes at time T" requirement on Starknet.
- Proving an expensive Cairo computation offchain and verifying it onchain cheaply (the Starknet-native pattern: `#[executable]` program → Stwo proof → Cairo recursive verifier).

The two halves are orthogonal:
- **Custody** (who can move funds) → shadow accounts, contract-gated escrow (see `strk20-privacy-integration` skill).
- **Reveal timing** (when amounts become readable) → this skill: RSW timelock + Wesolowski VDF.

For the full sealed-bid-auction design analysis (why bidder-side reveal griefs, the eBay-UX constraint, repo split decision, GitHub publishing notes), read `references/whisper-integration-design.md`.

## The scheme (validated, do not re-derive)

### RSW timelock encryption (encryptor fast, everyone else slow)
- Encryptor generates RSA modulus N = p·q, knows φ(N).
- Derives the timelock key instantly: y = x^(2^T mod φ(N)) mod N (O(log T)).
- Everyone else must compute y = x^(2^T) mod N by **T sequential squarings** — this is the delay.
- No trusted setup needed per-message: the encryptor is the only one who ever needs the factors, and can discard them after encryption. The bidder keeps their own bid secret from everyone including the auctioneer.

### Wesolowski VDF proof (verifier fast, O(log T) group ops)
- Prover computes y = x^(2^T) mod N (the T squarings) plus:
  - L = H(x, y, T) — hash-derived challenge (256-bit is fine for a 512–1024-bit N demo; production binds L onchain)
  - q = floor(2^T / L), r = 2^T mod L
  - π = x^q mod N
- Verifier checks: **y == π^L · x^(2^T mod L) (mod N)** — needs only two modpows with 256-bit exponents.

Reference implementation: `/tmp/vdf/ref/vdf_reference.py` (RSW + Wesolowski, generates vectors). Python model of the Cairo algorithm: `/tmp/vdf/ref/cairo_model_v2.py` (validate ANY algorithm change here first — it caught two real bugs before Cairo did).

## Cairo 2.20 bigint pattern (validated)

**Never use felt252 for bigint math.** felt252 has no `PartialOrd`, no `Rem`, no shifts, and `/` is field division. Instead:

- **Limbs**: `u64`, little-endian.
- **Multiplication**: accumulate in `u256` (products of two u64 fit; sums of ≤17 products < 2^133 fit u256).
- **Carry**: `acc & 0xffffffffffffffff_u256` → u64, `acc / 0x10000000000000000_u256` for carry — constant-divisor division on u256 is integer division.
- **Subtraction with borrow**: compute in `u128` (`minuend >= subtrahend` branch; add 2^64 when borrow needed). The borrow goes on the **subtrahend**, not the minuend — this was a real bug.
- **Bit scan in modpow**: `e % 2` / `e / 2` loop (u64), not shifts.
- **Barrett reduction**: mu = floor(b^(2k)/N) with k+1 limbs, computed offchain and passed in. Each modulus gets its own limb domain (N=16 limbs for 1024-bit, L=4 limbs for 256-bit) — mixing domains broke r_calc with an infinite normalize loop.

Core file: `lib/src/lib.cairo` — `bigint_mul`, `ge_limbs`, `sub_limbs`, `barrett_reduce`, `modmul`, `modpow`, `limbs_eq`, `verify_vdf`. All pub.

## Toolchain: scarb 2.20 executable + Stwo proving

### Setup (gotchas are real)
```
# exec/Scarb.toml — executable package
[[target.executable]]          # REQUIRED
[cairo]
enable-gas = false             # REQUIRED — executable target refuses gas
[dependencies]
cairo_execute = ">=2.20.0"     # the plugin that provides #[executable]
```

- **Workspaces break gas config**: per-package `[cairo]` and `[profile]` are ignored inside a workspace — only the workspace manifest's `[cairo]` applies. Split lib (tests need gas) and exec (gas off) into **two standalone packages** with a path dependency: `vdf = { path = "../lib" }`. No root workspace file at all.
- **Cairo 2.20 prelude**: do NOT `use array::ArrayTrait;` or `use option::OptionTrait;` — they're in the prelude; importing by those paths fails with E0006.
- **No closures** capturing mutable state — use a plain helper returning a tuple.
- **Tests**: `cairo-test` caps gas at 2^32. Heavy pure-computation programs (16-limb modpows) exceed it → validate via `scarb execute` (gas off), not tests. `scarb cairo-test` is deprecated → snforge eventually.

### The proving pipeline
```
scarb execute --output=standard --arguments-file args.json
  → target/execute/<pkg>/executionN/prover_input.json
scarb prove --execution-id N
  → target/execute/<pkg>/executionN/proof/proof.json
scarb verify <path to proof.json>
```

- **Arguments file**: JSON array of **hex strings** (`0x...`), with a leading length felt for `Span<felt252>` params (serde reads length first). Decimal strings rejected; `Span` params need `[len, elem0, ...]`.
- **`--output=standard` is required** to emit prover_input.json; default is None (empty dirs, no error). `--output=cairo-pie` only works for the bootloader target.
- **OOM is the big one**: the prover input for a 1024-bit VDF (16-limb modpows, ~4.3B gas) is ~139MB+ and Stwo needs 10–17GB RAM to prove. Use a 512-bit test modulus (8 limbs, N_LIMBS=8) on small machines; prove the real thing on a 16GB+ box. The execution dir artifacts are portable — copy to a bigger machine and `scarb prove --execution-id N` there.
- `scarb-prove` binary needs `SCARB_TARGET_DIR` and `SCARB_PROFILE=dev` exported when invoked directly (the `scarb` shell sets them).

### Verification onchain (the end state)
- Rust verifier for offchain/CI.
- **Cairo verifier** (stwo-cairo ships one) — runs inside Cairo VM → recursive proving, onchain verification. This is what makes "prove offchain, verify onchain" work: the heavy computation never runs in a tx; the tx just verifies a small proof.

## Repo layout (standalone, per project decision)
```
vdf/
  lib/   # bigint + verify_vdf (pub, gas-enabled for tests)
  exec/  # #[executable] vdf_verify → depends on lib via path
  ref/   # python reference + cairo_model_v2.py + vectors + generators
```

## Workflow when extending

1. Change the Python model (`cairo_model_v2.py`) FIRST, validate against vectors + random difftests.
2. Port to `lib/src/lib.cairo` mirroring limb-for-limb.
3. Validate with `scarb execute` (not tests) on the smallest vector that fits memory.
4. Regenerate test/args files with the generator scripts.
5. Prove on a big machine; keep execution-dir artifacts portable.

## Pitfalls checklist

- [ ] borrow goes on subtrahend, not minuend
- [ ] per-modulus limb domains, mu has k+1 limbs
- [ ] felt252: no PartialOrd/Rem/shifts — u64/u256 only
- [ ] workspace overrides per-package [cairo] — two standalone packages instead
- [ ] no ArrayTrait/OptionTrait imports in 2.20
- [ ] args = hex strings + leading length felt
- [ ] `--output=standard` or no prover_input.json
- [ ] cairo-test gas cap 2^32 — use scarb execute for heavy programs
- [ ] OOM on small machines — 512-bit modulus for CI/demo, 1024+ for real
