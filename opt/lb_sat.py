"""Whole-circuit SAT lower bounds.

Mode 'fixed':     prove no <=N-gate circuit exists for a given remap.
Mode 'universal': remap is existentially quantified (any valid remap) --
                  UNSAT at N proves NO remap admits an N-gate circuit.
Run ascending N; each UNSAT raises the proven floor.

This is the source of the README's "proven floor: >=15 gates (fixed remap),
>=13 gates (any remap)" claim. Reproducing the full proof takes real time --
the reference run took ~8660s (~2.4h) to prove fixed N=14 UNSAT and ~43846s
(~12h) to prove universal N=12 UNSAT. Small N (<=10) proves in seconds to
minutes and is a reasonable smoke test that the mechanism itself is sound.

Usage: python3 lb_sat.py fixed|universal <lo> <hi> [conflict_budget]
  fixed:     loads the remap from best62.json (the actual netlist's remap).
  universal: remap is a free variable in the SAT formula, no netlist needed.
"""
import sys, json, time
from pysat.solvers import Cadical195
from pysat.formula import IDPool
from harness import HALF_VALUES

OPS = ('AND', 'OR', 'XOR', 'NOT')
VALUES = sorted(set(HALF_VALUES))  # 15 distinct: 0 once here; zero gets 2 codes


def build(n_gates, remap=None, universal=False):
    N = n_gates
    NI = 8
    pool = IDPool()
    cls = []
    R = 256

    def sv(i, j, k):
        return pool.id(('s', i, j, k))

    def ov(i, o):
        return pool.id(('o', i, o))

    def val(i, r):
        return pool.id(('v', i, r))

    def outv(t, x):
        return pool.id(('t', t, x))

    def selv(c, v):
        return pool.id(('m', c, v))

    def inbit(r, j):
        a, b = r >> 4, r & 15  # r = a*16+b
        code = a if j < 4 else b
        return (code >> (j % 4)) & 1

    nsig = NI + N

    for i in range(N):
        pairs = []
        for j in range(NI + i):
            for k in range(j, NI + i):
                pairs.append(sv(i, j, k))
        cls.append(pairs)
        ops = [ov(i, o) for o in range(4)]
        cls.append(ops)
        for a in range(4):
            for b in range(a + 1, 4):
                cls.append([-ops[a], -ops[b]])
        for j in range(NI + i):
            cls.append([-sv(i, j, j), ov(i, 3)])
            for k in range(j + 1, NI + i):
                cls.append([-sv(i, j, k), -ov(i, 3)])
        # no dangling: gate i must feed a later gate or an output
        users = []
        for i2 in range(i + 1, N):
            for j in range(NI + i2):
                for k in range(j, NI + i2):
                    if j == NI + i or k == NI + i:
                        users.append(sv(i2, j, k))
        for t in range(9):
            users.append(outv(t, NI + i))
        cls.append(users)

    def sigval(x, r):
        if x < NI:
            return ('const', inbit(r, x))
        return val(x - NI, r)

    for i in range(N):
        for j in range(NI + i):
            for k in range(j, NI + i):
                s = sv(i, j, k)
                for r in range(R):
                    a = sigval(j, r)
                    b = sigval(k, r)
                    v = val(i, r)
                    for o, opname in enumerate(OPS):
                        olit = ov(i, o)
                        if opname == 'NOT':
                            if j != k:
                                continue
                            if isinstance(a, tuple):
                                res = 1 - a[1]
                                cls.append([-s, -olit, v if res else -v])
                            else:
                                cls.append([-s, -olit, v, a])
                                cls.append([-s, -olit, -v, -a])
                            continue
                        if j == k:
                            continue
                        if isinstance(a, tuple) and isinstance(b, tuple):
                            av, bv = a[1], b[1]
                            res = {'AND': av & bv, 'OR': av | bv, 'XOR': av ^ bv}[opname]
                            cls.append([-s, -olit, v if res else -v])
                        elif isinstance(a, tuple) or isinstance(b, tuple):
                            c = a[1] if isinstance(a, tuple) else b[1]
                            x = b if isinstance(a, tuple) else a
                            if opname == 'AND':
                                if c == 0:
                                    cls.append([-s, -olit, -v])
                                else:
                                    cls.append([-s, -olit, v, -x])
                                    cls.append([-s, -olit, -v, x])
                            elif opname == 'OR':
                                if c == 1:
                                    cls.append([-s, -olit, v])
                                else:
                                    cls.append([-s, -olit, v, -x])
                                    cls.append([-s, -olit, -v, x])
                            else:
                                if c == 0:
                                    cls.append([-s, -olit, v, -x])
                                    cls.append([-s, -olit, -v, x])
                                else:
                                    cls.append([-s, -olit, v, x])
                                    cls.append([-s, -olit, -v, -x])
                        else:
                            if opname == 'AND':
                                cls.append([-s, -olit, -v, a])
                                cls.append([-s, -olit, -v, b])
                                cls.append([-s, -olit, v, -a, -b])
                            elif opname == 'OR':
                                cls.append([-s, -olit, v, -a])
                                cls.append([-s, -olit, v, -b])
                                cls.append([-s, -olit, -v, a, b])
                            else:
                                cls.append([-s, -olit, v, a, -b])
                                cls.append([-s, -olit, v, -a, b])
                                cls.append([-s, -olit, -v, a, b])
                                cls.append([-s, -olit, -v, -a, -b])

    # outputs
    for t in range(9):
        cls.append([outv(t, x) for x in range(nsig)])

    if not universal:
        # fixed remap: spec known per row
        for t in range(9):
            for r in range(R):
                a, b = r >> 4, r & 15
                want = ((remap[a] * remap[b]) & 511) >> t & 1
                for x in range(nsig):
                    sval = sigval(x, r)
                    if isinstance(sval, tuple):
                        if sval[1] != want:
                            cls.append([-outv(t, x)])
                    else:
                        cls.append([-outv(t, x), sval if want else -sval])
    else:
        # remap selectors: each code one value; nonzero values one code; zero two codes
        NV = len(VALUES)
        for c in range(16):
            cls.append([selv(c, v) for v in range(NV)])
            for v1 in range(NV):
                for v2 in range(v1 + 1, NV):
                    cls.append([-selv(c, v1), -selv(c, v2)])
        from pysat.card import CardEnc, EncType
        for v in range(NV):
            lits = [selv(c, v) for c in range(16)]
            bound = 2 if VALUES[v] == 0 else 1
            eq = CardEnc.equals(lits=lits, bound=bound, vpool=pool,
                                encoding=EncType.seqcounter)
            cls.extend(eq.clauses)
        # symmetry breaking: operand-swap symmetric anyway; fix value 12 to an
        # even code (breaks nothing about wire naming; mild)
        # spec: per row, per value pair -> output value vars
        wvar = {}
        for t in range(9):
            for r in range(R):
                wvar[(t, r)] = pool.id(('w', t, r))
                for x in range(nsig):
                    sval = sigval(x, r)
                    if isinstance(sval, tuple):
                        lit = None
                        if sval[1] == 1:
                            cls.append([-outv(t, x), wvar[(t, r)]])
                        else:
                            cls.append([-outv(t, x), -wvar[(t, r)]])
                    else:
                        cls.append([-outv(t, x), -sval, wvar[(t, r)]])
                        cls.append([-outv(t, x), sval, -wvar[(t, r)]])
        for r in range(R):
            a, b = r >> 4, r & 15
            for va in range(len(VALUES)):
                for vb in range(len(VALUES)):
                    prod = (VALUES[va] * VALUES[vb]) & 511
                    for t in range(9):
                        want = (prod >> t) & 1
                        w = wvar[(t, r)]
                        cls.append([-selv(a, va), -selv(b, vb), w if want else -w])
    return cls


def prove(n, remap=None, universal=False, conf=None):
    t0 = time.time()
    cls = build(n, remap, universal)
    t1 = time.time()
    with Cadical195(bootstrap_with=cls) as S:
        if conf:
            S.conf_budget(conf)
            r = S.solve_limited()
        else:
            r = S.solve()
    t2 = time.time()
    tag = 'universal' if universal else 'fixed'
    res = {True: 'SAT', False: 'UNSAT', None: 'UNDECIDED'}[r]
    print(f'[{tag}] N={n}: {res}  (encode {t1-t0:.0f}s, solve {t2-t1:.0f}s, '
          f'{len(cls)} clauses)', flush=True)
    return r


if __name__ == '__main__':
    mode = sys.argv[1]
    lo = int(sys.argv[2])
    hi = int(sys.argv[3])
    conf = int(sys.argv[4]) if len(sys.argv) > 4 else None
    remap = None
    if mode == 'fixed':
        remap = tuple(json.load(open('best62.json'))['remap'])
    for n in range(lo, hi + 1):
        r = prove(n, remap, universal=(mode == 'universal'), conf=conf)
        if r is not False:
            break
