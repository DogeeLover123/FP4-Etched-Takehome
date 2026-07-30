"""FP4 multiplier -- 62-gate netlist found by automated search.

This is not a hand design. Starting from last commit's 78-gate hand-built
netlist, an automated optimizer (don't-care-aware resubstitution + window
SAT resynthesis, see README.md for the methodology and why 62 is very
likely at or near the true minimum) found a smaller circuit that computes
the exact same function. It's a flat, opaque r1..r62 chain with no
recognizable structure -- that's expected, it's search output, not
something a person would write by hand.

"""
from harness import Builder, verify, gate_count, REMAP_FP4


def build_fp4():
    B = Builder()
    sa, e1a, e0a, ma = 'a3', 'a2', 'a1', 'a0'
    sb, e1b, e0b, mb = 'b3', 'b2', 'b1', 'b0'

    # alias into the roles the ported netlist expects -- free, just which
    # name points at which existing wire
    na0, na1, na2, na3 = e0a, e1a, ma, sa
    nb0, nb1, nb2, nb3 = e0b, e1b, mb, sb

    r1 = B.AND(na0, na1)
    r2 = B.AND(nb0, nb1)
    r3 = B.XOR(na0, nb0)
    r4 = B.AND(na0, nb0)
    r5 = B.XOR(na1, nb1)
    r6 = B.XOR(r4, r5)
    r7 = B.AND(na1, nb1)
    r8 = B.AND(r4, r5)
    r9 = B.XOR(na2, nb2)
    r10 = B.AND(r3, r6)
    r11 = B.OR(r7, r8)
    r12 = B.NOT(r11)
    r13 = B.XOR(r10, r12)
    r14 = B.AND(r6, r13)
    r15 = B.AND(r3, r13)
    r16 = B.XOR(r14, r13)
    r17 = B.XOR(r15, r16)
    r18 = B.AND(na2, nb2)
    r19 = B.AND(r17, r18)
    r20 = B.AND(r14, r18)
    r21 = B.AND(r3, r11)
    r22 = B.AND(r9, r21)
    r23 = B.XOR(na3, nb3)
    r24 = B.AND(r17, r23)
    r25 = B.AND(na2, r1)
    r26 = B.AND(nb2, r2)
    r27 = B.OR(r25, r26)
    r28 = B.NOT(r27)
    r29 = B.AND(r23, r28)
    r30 = B.AND(r18, r11)
    r31 = B.AND(r9, r15)
    r32 = B.AND(r10, r18)
    r33 = B.OR(r3, r9)
    r34 = B.AND(r6, r33)
    r35 = B.AND(r33, r11)
    r36 = B.AND(r16, r33)
    r37 = B.AND(r23, r13)
    r38 = B.OR(r14, r37)
    r39 = B.AND(r9, r10)
    r40 = B.AND(r15, r18)
    r41 = B.AND(r6, r11)
    r42 = B.OR(r23, r11)
    r43 = B.XOR(r41, r42)
    r44 = B.XOR(r21, r43)
    r45 = B.AND(r23, r44)
    r46 = B.XOR(r32, r23)
    r47 = B.OR(r19, r34)
    r48 = B.OR(r39, r40)
    r49 = B.OR(r20, r35)
    r50 = B.XOR(r22, r46)
    r51 = B.XOR(r37, r47)
    r52 = B.XOR(r44, r48)
    r53 = B.XOR(r45, r49)
    r54 = B.OR(r41, r50)
    r55 = B.XOR(r30, r23)
    r56 = B.XOR(r24, r36)
    r57 = B.AND(r28, r51)
    r58 = B.AND(r28, r52)
    r59 = B.AND(r28, r53)
    r60 = B.AND(r28, r54)
    r61 = B.AND(r28, r55)
    r62 = B.XOR(r31, r38)

    outputs = [r17, r56, r62, r57, r58, r59, r60, r61, r29]
    return B.gates, outputs


if __name__ == '__main__':
    gates, outputs = build_fp4()
    ok = verify(REMAP_FP4, gates, outputs)
    n = gate_count(gates)
    print(f'fp4 multiplier: {n} gates, '
          f'{"all 256 cases pass" if ok else "FAILED"}')
