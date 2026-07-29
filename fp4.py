"""FP4 multiplier — current stage: deliberately BLOATED baseline, no remapping.

Same architecture/dataflow as any general-purpose FP multiplier on the
standard FP4 (E2M1) encoding `(s, e1, e0, m)`:

    unsigned = zero_fill_9( significand_product << (Ea + Eb - 2) )
    signed   = two's complement of unsigned, if (sa XOR sb)

but every stage is built from genuinely generic, textbook sub-blocks —
full adders (not half adders), unconditional 2:1 muxes (not constant-folded
logic), and a REAL barrel shifter (shift-by-a-signal is not free; it is the
single most expensive block here). This file exists to make honest the gap
that later commits close by hand-optimizing (and eventually remapping +
SAT-searching) the same function.

This file will be improved *in place* over future commits.
"""
from harness import Builder, verify, gate_count, STANDARD_FP4


def full_adder(B, a, b, cin):
    """Textbook 1-bit full adder: 2 XOR, 2 AND, 1 OR = 5 gates."""
    axb = B.XOR(a, b)
    s = B.XOR(axb, cin)
    c1 = B.AND(a, b)
    c2 = B.AND(axb, cin)
    cout = B.OR(c1, c2)
    return s, cout


def mux2(B, i0, i1, sel):
    """Textbook 2:1 mux: NOT, AND, AND, OR = 4 gates. No input-collapsing."""
    nsel = B.NOT(sel)
    a = B.AND(i0, nsel)
    b = B.AND(i1, sel)
    return B.OR(a, b)


def is_zero2(B, hi, lo):
    """Equality-to-00 for a 2-bit value: NOT(hi | lo) = 2 gates."""
    return B.NOT(B.OR(hi, lo))


def ripple_add(B, xs, ys, cin='CONST0'):
    """Generic ripple-carry adder over two equal-length bit lists (LSB first).
    Every bit uses a real full_adder, even where an input is a known constant."""
    outs = []
    c = cin
    for x, y in zip(xs, ys):
        s, c = full_adder(B, x, y, c)
        outs.append(s)
    return outs, c


def const_bits(B, value, width):
    return [('CONST1' if (value >> i) & 1 else 'CONST0') for i in range(width)]


def build_fp4():
    B = Builder()
    sa, e1a, e0a, ma = 'a3', 'a2', 'a1', 'a0'
    sb, e1b, e0b, mb = 'b3', 'b2', 'b1', 'b0'

    # --- significand + effective exponent, via generic building blocks ---
    za = is_zero2(B, e1a, e0a)   # is operand A subnormal (e==0)?
    zb = is_zero2(B, e1b, e0b)
    hia = B.NOT(za)              # significand hi bit: 1 unless subnormal
    hib = B.NOT(zb)
    loa, lob = ma, mb

    # effective exponent = max(e, 1): mux each bit between e and the constant 01
    one_bits = const_bits(B, 1, 2)  # [lo, hi] = [1, 0]
    Ea1 = mux2(B, e1a, one_bits[1], za)
    Ea0 = mux2(B, e0a, one_bits[0], za)
    Eb1 = mux2(B, e1b, one_bits[1], zb)
    Eb0 = mux2(B, e0b, one_bits[0], zb)

    # --- 2x2-bit significand multiplier, full-adder cost (cin wired to 0) ---
    pp0 = B.AND(loa, lob)
    pp1 = B.AND(loa, hib)
    pp2 = B.AND(hia, lob)
    pp3 = B.AND(hia, hib)
    MP0 = pp0
    MP1, c1 = full_adder(B, pp1, pp2, 'CONST0')
    MP2, MP3 = full_adder(B, pp3, c1, 'CONST0')

    # --- exponent add (real ripple adder), then real subtract of constant 2 ---
    SH, SHc = ripple_add(B, [Ea0, Ea1], [Eb0, Eb1])   # 2-bit + 2-bit -> 2-bit sum + carry
    SH_bits = [SH[0], SH[1], SHc]                      # 3-bit sum, range [0,6]
    # subtract constant 2: add two's complement of 2 over 3 bits (~010 + 1 = 101)
    neg2_bits = const_bits(B, (-2) & 7, 3)
    K_bits, _ = ripple_add(B, SH_bits, neg2_bits, cin='CONST0')
    K0, K1, K2 = K_bits  # range [0,4]

    # --- real 3-stage barrel shifter: MP << K, no zero-fill shortcuts ---
    MP = [MP0, MP1, MP2, MP3]

    def shift_stage(bits, amount, sel):
        """bits shifted left by `amount` if sel else unchanged; every output
        bit is a genuine mux2, including where an input is constant 0."""
        width = len(bits) + amount
        padded_in = ['CONST0'] * amount + bits + ['CONST0'] * 0
        unshifted = bits + ['CONST0'] * amount
        out = []
        for i in range(width):
            i0 = unshifted[i] if i < len(unshifted) else 'CONST0'
            i1 = padded_in[i] if i < len(padded_in) else 'CONST0'
            out.append(mux2(B, i0, i1, sel))
        return out

    S1 = shift_stage(MP, 1, K0)   # width 5
    S2 = shift_stage(S1, 2, K1)   # width 7
    U = shift_stage(S2, 4, K2)    # width 9  (max value 9<<4 = 144, fits)
    while len(U) < 9:
        U.append('CONST0')

    # --- sign + conditional two's complement, all via generic blocks ---
    s = B.XOR(sa, sb)
    inv = [B.NOT(u) for u in U]
    plus1_const = const_bits(B, 1, 9)
    incremented, _ = ripple_add(B, inv, plus1_const)
    out = [mux2(B, U[i], incremented[i], s) for i in range(9)]
    return B.gates, out


if __name__ == '__main__':
    gates, outputs = build_fp4()
    ok = verify(STANDARD_FP4, gates, outputs)
    n = gate_count(gates)
    print(f'fp4 multiplier (bloated baseline): {n} gates, '
          f'{"all 256 cases pass" if ok else "FAILED"}')
