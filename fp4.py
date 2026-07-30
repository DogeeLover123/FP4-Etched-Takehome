"""FP4 multiplier -- input remapped to (s, m, e1, e0).

value = (-1)^s * (1 + 2m) * 2^(e-1), with (m=1, e=3) reused as the zero code
(both signs) since 3*2^3=24 isn't a real fp4 magnitude. See harness.py's
REMAP_FP4 for the code -> value table, README.md for the full derivation.

For nonzero operands: 4*va*vb = (-1)^s * 3^K * 2^E, K = ma+mb in {0,1,2},
E = ea+eb in [0,6] -- no -2 correction needed this time, the "-1" baked into
the value formula and the spec's "*4" cancel exactly. 3^K in {1,3,9} is just
a constant 4-bit pattern selected by K, so no real significand multiplier is
needed at all (K only takes 3 values).

Still using the same barrel-shifter + XOR-negate machinery as the last two
commits for now -- the shift-in-zero and negation-specific tricks are next
commit.
"""
from harness import Builder, verify, gate_count, REMAP_FP4


def build_fp4():
    B = Builder()
    sa, e1a, e0a, ma = 'a3', 'a2', 'a1', 'a0'
    sb, e1b, e0b, mb = 'b3', 'b2', 'b1', 'b0'

    # zero iff (m=1, e=3) -- a 3-input AND per operand
    za = B.AND(ma, B.AND(e1a, e0a))
    zb = B.AND(mb, B.AND(e1b, e0b))
    nz = B.NOT(B.OR(za, zb))

    # sign
    s = B.XOR(sa, sb)

    # E = ea + eb, plain 2-bit + 2-bit adder, no correction needed
    E0 = B.XOR(e0a, e0b)
    c0 = B.AND(e0a, e0b)
    t = B.XOR(e1a, e1b)
    E1 = B.XOR(t, c0)
    g = B.AND(e1a, e1b)
    p = B.AND(t, c0)
    E2 = B.OR(g, p)

    # K = ma + mb in {0,1,2} -> 3^K is a fixed 4-bit pattern (1,3,9) picked
    # by K, no multiplier needed: bit0 always set, bit1 set iff K==1 (K0),
    # bit3 set iff K==2 (K1), bit2 never set
    K0 = B.XOR(ma, mb)
    K1 = B.AND(ma, mb)
    MP = ['CONST1', K0, 'CONST0', K1]

    # barrel-shift MP (4 bits) by E (0..6) into a 9-bit field -- same
    # 3-stage style as before (shifted-in bits are known 0, so most muxes
    # collapse to a single AND)
    def shift_stage(bits, sel, amount):
        n = B.NOT(sel)
        out = []
        for j in range(len(bits) + amount):
            hi = bits[j] if j < len(bits) else None
            lo = bits[j - amount] if 0 <= j - amount < len(bits) else None
            if hi is not None and lo is not None:
                out.append(B.OR(B.AND(hi, n), B.AND(lo, sel)))
            elif hi is not None:
                out.append(B.AND(hi, n))
            else:
                out.append(B.AND(lo, sel))
        return out

    S1 = shift_stage(MP, E0, 1)
    S2 = shift_stage(S1, E1, 2)
    U = shift_stage(S2, E2, 4)[:9]

    # sign + conditional two's complement, folded into one XOR+ripple-carry
    # pass, then mask the whole result with ~is_zero
    y = [B.XOR(u, s) for u in U]
    out = [B.XOR(y[0], s)]
    carry = B.AND(y[0], s)
    for j in range(1, 9):
        out.append(B.XOR(y[j], carry))
        if j < 8:
            carry = B.AND(y[j], carry)
    out = [B.AND(o, nz) for o in out]
    return B.gates, out


if __name__ == '__main__':
    gates, outputs = build_fp4()
    ok = verify(REMAP_FP4, gates, outputs)
    n = gate_count(gates)
    print(f'fp4 multiplier: {n} gates, '
          f'{"all 256 cases pass" if ok else "FAILED"}')
