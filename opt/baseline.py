"""Hand-designed baseline: thermometer / XOR-derivative construction.

This is the optimizer's starting point -- the 78-gate hand design (same
architecture as the top-level repo's commit-2 fp4.py, just built under this
folder's own bit-order convention: code bits (b3,b2,b1,b0) = (s,m,e1,e0),
matching remap_sme() in abc_flow.py).

value*2 = (-1)^s * (1+2m) * 2^e, zero at (m=1, e=3) for both signs.
Product*4 = (-1)^S * 3^K * 2^E with S = sa^sb, K = # of 3-mantissas, E = ea+eb.
3^K*2^E = 2^E + [K>=1]*2^(E+2K-1)  (two non-colliding powers of 2).
Negation: for P with lowest set bit E, (-P)_j = P_j ^ (S & [j > E]).
Thermometer t_j = [E <= j]; onehot d_j = t_j ^ t_{j-1}.
out_j = (P_j ^ (S & t_{j-1})) & ~zero.
"""
from harness import Builder, verify, gate_count
from abc_flow import remap_sme


def build_baseline():
    B = Builder()
    sa, ma, e1a, e0a = 'a3', 'a2', 'a1', 'a0'
    sb, mb, e1b, e0b = 'b3', 'b2', 'b1', 'b0'

    # zero flags
    za = B.AND(ma, B.AND(e1a, e0a))
    zb = B.AND(mb, B.AND(e1b, e0b))
    z = B.OR(za, zb)
    nz = B.NOT(z)

    # sign
    s = B.XOR(sa, sb)

    # exponent adder: E = ea + eb (E2 E1 E0)
    E0 = B.XOR(e0a, e0b)
    c0 = B.AND(e0a, e0b)
    t = B.XOR(e1a, e1b)
    E1 = B.XOR(t, c0)
    g = B.AND(e1a, e1b)
    p = B.AND(t, c0)
    E2 = B.OR(g, p)

    # mantissa-3 counters
    k1 = B.XOR(ma, mb)
    k2 = B.AND(ma, mb)

    # thermometer t_j = [E <= j]
    nE2 = B.NOT(E2)
    u = B.OR(E1, E0)
    v = B.AND(E1, E0)
    t0 = B.NOT(B.OR(E2, u))
    t1 = B.NOT(B.OR(E2, E1))
    t2 = B.AND(nE2, B.NOT(v))
    t3 = nE2
    t4 = B.NOT(B.AND(E2, u))
    t5 = B.NOT(B.AND(E2, E1))
    t6 = 'CONST1'
    t7 = 'CONST1'
    T = [t0, t1, t2, t3, t4, t5, t6, t7]

    # onehot
    d = [t0]
    for j in range(1, 7):
        d.append(B.XOR(T[j], T[j - 1]))
    d.append('CONST0')  # d7

    # unsigned product bits P_j = d_j | k1&d_{j-1} | k2&d_{j-3}
    P = [None] * 9
    P[0] = d[0]
    for j in range(1, 7):
        acc = B.OR(d[j], B.AND(k1, d[j - 1]))
        if j >= 3:
            acc = B.OR(acc, B.AND(k2, d[j - 3]))
        P[j] = acc
    P[7] = B.AND(k2, d[4])
    P[8] = 'CONST0'

    # signed output with zero mask
    out = []
    Tm1 = ['CONST0'] + T  # t_{j-1}
    for j in range(9):
        core = B.XOR(P[j], B.AND(s, Tm1[j]))
        out.append(B.AND(core, nz))
    return B.gates, out


if __name__ == '__main__':
    remap = remap_sme()
    gates, outputs = build_baseline()
    ok = verify(remap, gates, outputs, verbose=True)
    print(f'baseline: {gate_count(gates)} gates, verified={ok}')
