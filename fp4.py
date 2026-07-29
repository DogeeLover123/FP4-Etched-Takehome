"""FP4 multiplier -- standard FP4 encoding, no input remapping yet.

Same architecture/dataflow as before:

    unsigned = zero_fill_9( significand_product << (Ea + Eb - 2) )
    signed   = two's complement of unsigned, if (sa XOR sb)

but now actually exploiting constants and correlations instead of using
generic full adders / unconditional muxes everywhere -- see rtl/fp4.sv
header for the reasoning behind each change.
"""
from harness import Builder, verify, gate_count, STANDARD_FP4


def build_fp4():
    B = Builder()
    sa, e1a, e0a, ma = 'a3', 'a2', 'a1', 'a0'
    sb, e1b, e0b, mb = 'b3', 'b2', 'b1', 'b0'

    # significand hi bit = "not subnormal" = e1 | e0 directly, no is_zero needed
    hia = B.OR(e1a, e0a)
    hib = B.OR(e1b, e0b)
    loa, lob = ma, mb

    # effective exponent = max(e,1): Ea1 = e1, Ea0 = e0 | ~e1 (no real mux needed --
    # if e1 is 1 the value is already >=2 so e0 doesn't matter; if e1 is 0 we want e0|1's-bit)
    Ea1, Eb1 = e1a, e1b
    Ea0 = B.OR(e0a, B.NOT(e1a))
    Eb0 = B.OR(e0b, B.NOT(e1b))

    # 2x2-bit significand multiply
    pp0 = B.AND(loa, lob)
    pp1 = B.AND(loa, hib)
    pp2 = B.AND(hia, lob)
    pp3 = B.AND(hia, hib)
    MP0 = pp0
    MP1 = B.XOR(pp1, pp2)
    c1 = B.AND(pp1, pp2)
    MP2 = B.XOR(pp3, c1)
    MP3 = B.AND(pp3, c1)

    # exponent add, then fold the constant -2 straight into the adder outputs
    SH0 = B.XOR(Ea0, Eb0)
    c0 = B.AND(Ea0, Eb0)
    t = B.XOR(Ea1, Eb1)
    SH1 = B.XOR(t, c0)
    g = B.AND(Ea1, Eb1)
    p = B.AND(t, c0)
    SH2 = B.OR(g, p)
    K0 = SH0
    K1 = B.NOT(SH1)
    K2 = B.XOR(SH2, K1)

    # barrel shifter -- shifted-in bits are known 0, so most muxes collapse to one AND
    n0 = B.NOT(K0)
    S1 = [B.AND(MP0, n0),
          B.OR(B.AND(MP1, n0), B.AND(MP0, K0)),
          B.OR(B.AND(MP2, n0), B.AND(MP1, K0)),
          B.OR(B.AND(MP3, n0), B.AND(MP2, K0)),
          B.AND(MP3, K0)]
    n1 = B.NOT(K1)
    S2 = [B.AND(S1[0], n1),
          B.AND(S1[1], n1),
          B.OR(B.AND(S1[2], n1), B.AND(S1[0], K1)),
          B.OR(B.AND(S1[3], n1), B.AND(S1[1], K1)),
          B.OR(B.AND(S1[4], n1), B.AND(S1[2], K1)),
          B.AND(S1[3], K1),
          B.AND(S1[4], K1)]
    n2 = B.NOT(K2)
    U = [B.AND(S2[0], n2),
         B.AND(S2[1], n2),
         B.AND(S2[2], n2),
         B.AND(S2[3], n2),
         B.OR(B.AND(S2[4], n2), B.AND(S2[0], K2)),
         B.OR(B.AND(S2[5], n2), B.AND(S2[1], K2)),
         B.OR(B.AND(S2[6], n2), B.AND(S2[2], K2)),
         B.AND(S2[3], K2),
         'CONST0']

    # sign + conditional two's complement, folded into one XOR+ripple-carry pass
    # instead of inverting, adding 1, and muxing between two branches
    s = B.XOR(sa, sb)
    y = [B.XOR(u, s) for u in U]
    out = [B.XOR(y[0], s)]
    carry = B.AND(y[0], s)
    for j in range(1, 9):
        out.append(B.XOR(y[j], carry))
        if j < 8:
            carry = B.AND(y[j], carry)
    return B.gates, out


if __name__ == '__main__':
    gates, outputs = build_fp4()
    ok = verify(STANDARD_FP4, gates, outputs)
    n = gate_count(gates)
    print(f'fp4 multiplier: {n} gates, '
          f'{"all 256 cases pass" if ok else "FAILED"}')
