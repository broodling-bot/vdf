use vdf::{verify_vdf, N_LIMBS, L_LIMBS};

/// Slice `n` felts starting at `offset` into u64 limbs, returning the array
/// and the new offset.
fn take_u64s(inputs: Span<felt252>, offset: usize, n: usize) -> (Array<u64>, usize) {
    let mut out = ArrayTrait::new();
    let mut j: usize = 0;
    while j < n {
        let v: u64 = (*inputs.at(offset + j)).try_into().unwrap();
        out.append(v);
        j += 1;
    }
    (out, offset + n)
}

/// Executable entrypoint: flat felt252 inputs [N(16), mu_n(17), x(16), y(16),
/// pi(16), L(4), mu_l(5), r(4), T(2)], returns 1 if the VDF proof verifies.
#[executable]
pub fn vdf_verify(inputs: Span<felt252>) -> felt252 {
    let (N, off) = take_u64s(inputs, 0, N_LIMBS);
    let (mu_n, off) = take_u64s(inputs, off, N_LIMBS + 1);
    let (x, off) = take_u64s(inputs, off, N_LIMBS);
    let (y, off) = take_u64s(inputs, off, N_LIMBS);
    let (pi, off) = take_u64s(inputs, off, N_LIMBS);
    let (L, off) = take_u64s(inputs, off, L_LIMBS);
    let (mu_l, off) = take_u64s(inputs, off, L_LIMBS + 1);
    let (r, off) = take_u64s(inputs, off, L_LIMBS);
    let (T, _) = take_u64s(inputs, off, 2);

    if verify_vdf(
        N.span(), mu_n.span(), x.span(), y.span(), pi.span(), L.span(), mu_l.span(), r.span(),
        T.span(), 2,
    ) {
        1
    } else {
        0
    }
}
