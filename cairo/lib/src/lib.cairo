/// Wesolowski VDF verifier over an RSA-style modulus, as a Cairo *executable*
/// (not a contract). This is the program you prove with stwo-cairo: run it
/// offchain, produce a CairoProof, and verify the proof onchain via the Cairo
/// verifier (recursive) or a Rust verifier — proving that the T sequential
/// squarings happened without ever running them in a Starknet tx.
///
/// Scheme:
///   prover computes y = x^(2^T) mod N (T sequential squarings, offchain)
///   and pi = x^floor(2^T / L) mod N where L = H(x, y, T).
///   verifier checks, in O(log T) group ops:
///     r = 2^T mod L
///     pi^L * x^r == y  (mod N)
///
/// Combined with RSW timelock encryption (encryptor knows phi(N) and derives
/// the key instantly; everyone else must square T times), this gives "decryption
/// capability materializes at the deadline" with no standing decryptor, no
/// committee, and no TEE.
///
/// Big-int representation: little-endian limbs of 64 bits. Two limb domains:
///   N (1024-bit modulus)       -> N_LIMBS = 16
///   L (256-bit challenge)      -> L_LIMBS = 4
/// Barrett reduction uses mu = floor(b^(2k)/N) with k+1 limbs, computed
/// offchain and passed in.
///
/// Cairo constraints honored: limbs are u64 (supports shift/compare/bitand),
/// multiplication accumulates in u256 (products of two u64s fit comfortably),
/// subtraction borrow logic mirrors the validated Python model.

pub const LIMB_BITS: u32 = 64;
pub const N_LIMBS: usize = 8; // 512-bit RSA modulus (demo/CI); 16 for 1024-bit production
pub const L_LIMBS: usize = 4;

/// Schoolbook multiplication: full (an+bn)-limb product, one limb at a time
/// with a chained u256 carry. Mirrors cairo_model_v2.bigint_mul exactly.
pub fn bigint_mul(a: Span<u64>, b: Span<u64>, an: usize, bn: usize) -> Array<u64> {
    let total = an + bn;
    let mut out = ArrayTrait::new();
    let mut carry: u256 = 0;
    let mut t: usize = 0;
    while t < total {
        // acc = carry_in + sum_{i+j==t} a[i]*b[j]
        let mut acc: u256 = carry;
        let mut i: usize = 0;
        while i < an {
            if i <= t {
                let j = t - i;
                if j < bn {
                    let ai: u256 = (*a.at(i)).into();
                    let bj: u256 = (*b.at(j)).into();
                    acc += ai * bj;
                }
            }
            i += 1;
        }
        let limb: u64 = (acc & 0xffffffffffffffff_u256).try_into().unwrap();
        out.append(limb);
        carry = acc / 0x10000000000000000_u256;
        t += 1;
    }
    out
}

/// True if a >= b (both k limbs, big-endian comparison).
pub fn ge_limbs(a: Span<u64>, b: Span<u64>, k: usize) -> bool {
    let mut i = k;
    loop {
        if i == 0 {
            break;
        }
        i -= 1;
        let ai = *a.at(i);
        let bi = *b.at(i);
        if ai != bi {
            return ai > bi;
        }
    };
    true // equal
}

/// Limb-wise a - b with borrow, k limbs, u128-safe arithmetic.
pub fn sub_limbs(a: Span<u64>, b: Span<u64>, k: usize) -> Array<u64> {
    let mut out = ArrayTrait::new();
    let mut borrow: u64 = 0;
    let mut i: usize = 0;
    while i < k {
        let minuend: u128 = (*a.at(i)).into();
        let subtrahend: u128 = (*b.at(i)).into() + borrow.into();
        if minuend >= subtrahend {
            out.append((minuend - subtrahend).try_into().unwrap());
            borrow = 0;
        } else {
            out.append((minuend + 0x10000000000000000_u128 - subtrahend).try_into().unwrap());
            borrow = 1;
        }
        i += 1;
    }
    out
}

/// Barrett reduction of a 2k-limb product p modulo k-limb N.
/// mu = floor(b^(2k)/N) with k+1 limbs, precomputed offchain.
pub fn barrett_reduce(
    p: Span<u64>, N: Span<u64>, mu: Span<u64>, k: usize,
) -> Array<u64> {
    // q1 = p >> (k-1)   (k+1 limbs)
    let mut q1 = ArrayTrait::new();
    let mut i: usize = k - 1;
    while i < 2 * k {
        q1.append(*p.at(i));
        i += 1;
    }

    // q2 = q1 * mu      (2k+2 limbs)
    let q2 = bigint_mul(q1.span(), mu, k + 1, k + 1);

    // q3 = q2 >> (k+1)  (k+1 limbs)
    let mut q3 = ArrayTrait::new();
    i = k + 1;
    while i < 2 * k + 2 {
        q3.append(*q2.at(i));
        i += 1;
    }

    // q3n = q3 * N      (2k+1 limbs)
    let q3n = bigint_mul(q3.span(), N, k + 1, k);

    // r = (p - q3n) mod b^k with borrow
    let mut r = ArrayTrait::new();
    let mut borrow: u64 = 0;
    i = 0;
    while i < k {
        let minuend: u128 = (*p.at(i)).into();
        let subtrahend: u128 = (*q3n.at(i)).into() + borrow.into();
        if minuend >= subtrahend {
            r.append((minuend - subtrahend).try_into().unwrap());
            borrow = 0;
        } else {
            r.append((minuend + 0x10000000000000000_u128 - subtrahend).try_into().unwrap());
            borrow = 1;
        }
        i += 1;
    }

    // normalize: while r >= N, r -= N  (at most 2 iterations)
    let mut iter: usize = 0;
    while iter < 2 {
        if ge_limbs(r.span(), N, k) {
            r = sub_limbs(r.span(), N, k);
        }
        iter += 1;
    }
    r
}

/// Modular multiplication: a*b mod N. a, b < N < b^k.
pub fn modmul(
    a: Span<u64>, b: Span<u64>, N: Span<u64>, mu: Span<u64>, k: usize,
) -> Array<u64> {
    let p = bigint_mul(a, b, k, k);
    barrett_reduce(p.span(), N, mu, k)
}

/// Modular exponentiation: base^exp mod N, square-and-multiply over the bits
/// of the (exp_n-limb) exponent.
pub fn modpow(
    base: Span<u64>,
    exp: Span<u64>,
    exp_n: usize,
    N: Span<u64>,
    mu: Span<u64>,
    k: usize,
) -> Array<u64> {
    // one = 1 in the k-limb domain
    let mut one = ArrayTrait::new();
    one.append(1);
    let mut i: usize = 1;
    while i < k {
        one.append(0);
        i += 1;
    }
    let mut result = barrett_reduce(bigint_mul(one.span(), one.span(), k, k).span(), N, mu, k);
    let mut base_red = modmul(base, one.span(), N, mu, k);

    i = 0;
    while i < exp_n {
        let mut e = *exp.at(i);
        let mut bit: u32 = 0;
        while bit < LIMB_BITS {
            if (e % 2) == 1 {
                result = modmul(result.span(), base_red.span(), N, mu, k);
            }
            base_red = modmul(base_red.span(), base_red.span(), N, mu, k);
            e = e / 2;
            bit += 1;
        }
        i += 1;
    }
    result
}

/// Compare two k-limb arrays for equality.
pub fn limbs_eq(a: Span<u64>, b: Span<u64>, k: usize) -> bool {
    let mut i: usize = 0;
    while i < k {
        if *a.at(i) != *b.at(i) {
            return false;
        }
        i += 1;
    }
    true
}

/// Wesolowski VDF verification core.
/// Returns true iff r = 2^T mod L recomputes correctly AND pi^L * x^r == y mod N.
pub fn verify_vdf(
    N: Span<u64>,
    mu_n: Span<u64>,
    x: Span<u64>,
    y: Span<u64>,
    pi: Span<u64>,
    L: Span<u64>,
    mu_l: Span<u64>,
    r: Span<u64>,
    T_limbs: Span<u64>,
    T_n: usize,
) -> bool {
    // 1. recompute r = 2^T mod L in the L domain
    let mut two = ArrayTrait::new();
    two.append(2);
    let mut i: usize = 1;
    while i < L_LIMBS {
        two.append(0);
        i += 1;
    }
    let r_calc = modpow(two.span(), T_limbs, T_n, L, mu_l, L_LIMBS);
    if !limbs_eq(r_calc.span(), r, L_LIMBS) {
        return false;
    }

    // 2. lhs = pi^L * x^r mod N
    let pi_l = modpow(pi, L, L_LIMBS, N, mu_n, N_LIMBS);
    let x_r = modpow(x, r, L_LIMBS, N, mu_n, N_LIMBS);
    let lhs = modmul(pi_l.span(), x_r.span(), N, mu_n, N_LIMBS);

    // 3. check lhs == y
    limbs_eq(lhs.span(), y, N_LIMBS)
}

mod tests;
