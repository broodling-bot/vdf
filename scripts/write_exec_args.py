#!/usr/bin/env python3
"""Write exec args for a given vector index (hex with Span length prefix)."""
import json
import sys

sys.path.insert(0, "/tmp/vdf")
from gen_cairo_tests import barrett_mu  # noqa: E402

idx = int(sys.argv[1]) if len(sys.argv) > 1 else 0
out = sys.argv[2] if len(sys.argv) > 2 else "/tmp/vdf/exec_args.json"

VECTORS = json.load(open("/tmp/vdf/vdf_vectors.json"))
v = VECTORS[idx]
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
args = ["0x%x" % len(flat)] + ["0x%x" % x for x in flat]
json.dump(args, open(out, "w"))
print(f"vector {idx} ({v['name']}): {len(flat)} felts -> {out}")
