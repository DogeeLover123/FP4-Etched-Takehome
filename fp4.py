"""FP4 multiplier -- thermometer-code negation trick.

Replaces last commit's separate barrel shifter + XOR-ripple negate with one
shared thermometer chain that does both jobs at once.

Thermometer code of E: t_j = [E <= j] for j in 0..7 (E in [0,6], so t6=t7=1
always). Two things fall out of it for free:

1. its XOR-derivative d_j = t_j ^ t_{j-1} is the one-hot decoder of E -- this
   IS the shifter, no mux tree needed, replaces the whole 3-stage barrel
   shifter from last commit.
2. for any unsigned value P whose lowest set bit sits at position E, two's
   complement negation is just "flip every bit above E when the result is
   negative": out_j = P_j ^ (s & t_{j-1}). So the same thermometer chain
   used to decode E also IS the negation mask -- no separate
   invert-add-select pass needed.

Zero also gets cheaper here: (m=1, e=3) forces E>=3, so t0..t2 (and
therefore d0..d2, and P0..P2) are already correct on a zero operand without
any masking. The final ~is_zero mask still runs uniformly over all 9 output
bits below, but several of those masks fold away for free wherever Tm1_j
happens to land on a literal constant (bits 0, 7, 8) -- see README.md gate
breakdown.
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

    # E = ea + eb, plain 2-bit + 2-bit adder
    E0 = B.XOR(e0a, e0b)
    c0 = B.AND(e0a, e0b)
    t = B.XOR(e1a, e1b)
    E1 = B.XOR(t, c0)
    g = B.AND(e1a, e1b)
    p = B.AND(t, c0)
    E2 = B.OR(g, p)

    # K = ma + mb in {0,1,2} -> bit1 of 3^K set iff K==1 (K0), bit3 set iff
    # K==2 (K1)
    K0 = B.XOR(ma, mb)
    K1 = B.AND(ma, mb)

    # thermometer code t_j = [E <= j]
    nE2 = B.NOT(E2)
    u = B.OR(E1, E0)
    v = B.AND(E1, E0)
    t0 = B.NOT(B.OR(E2, u))
    t1 = B.NOT(B.OR(E2, E1))
    t2 = B.AND(nE2, B.NOT(v))
    t3 = nE2
    t4 = B.NOT(B.AND(E2, u))
    t5 = B.NOT(B.AND(E2, E1))
    T = [t0, t1, t2, t3, t4, t5, 'CONST1', 'CONST1']

    # onehot decoder d_j = t_j ^ t_{j-1} -- this replaces the barrel shifter
    d = [t0]
    for j in range(1, 7):
        d.append(B.XOR(T[j], T[j - 1]))
    d.append('CONST0')  # E never reaches 7, so d7 is always 0

    # unsigned product bits: bit0 of 3^K always set -> d_j; bit1 set iff
    # K==1 -> K0 & d_{j-1}; bit3 set iff K==2 -> K1 & d_{j-3}
    P = [None] * 9
    P[0] = d[0]
    for j in range(1, 7):
        acc = B.OR(d[j], B.AND(K0, d[j - 1]))
        if j >= 3:
            acc = B.OR(acc, B.AND(K1, d[j - 3]))
        P[j] = acc
    P[7] = B.AND(K1, d[4])
    P[8] = 'CONST0'

    # signed output: flip bits above E when negative (same thermometer
    # chain used for the shift), then mask to 0 if either operand was zero
    out = []
    Tm1 = ['CONST0'] + T
    for j in range(9):
        core = B.XOR(P[j], B.AND(s, Tm1[j]))
        out.append(B.AND(core, nz))
    return B.gates, out


if __name__ == '__main__':
    gates, outputs = build_fp4()
    ok = verify(REMAP_FP4, gates, outputs)
    n = gate_count(gates)
    print(f'fp4 multiplier: {n} gates, '
          f'{"all 256 cases pass" if ok else "FAILED"}')
