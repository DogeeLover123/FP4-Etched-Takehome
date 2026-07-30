"""SAT-based exact synthesis of small multi-output blocks over {AND, OR, XOR, NOT}.

Boolean-chain encoding: gate i picks an ordered pair of fanins among
inputs+earlier gates, and an op. Row-wise value variables tie semantics.
Targets have per-row care masks (don't-cares supported).

Requires the `python-sat` package (pysat) with the Cadical195 backend.
"""
from pysat.solvers import Cadical195
from pysat.formula import IDPool


OPS = ('AND', 'OR', 'XOR', 'NOT')


def synth(input_rows, targets, n_gates, solver_time=None, rng=None, forbid=None,
          sym_break=True, allow_const_outputs=False, status_out=None, hint=None):
    """
    input_rows: list of tuples, each tuple = values of the block inputs for one row.
    targets: list of (spec_bits_per_row, care_bits_per_row) per output, as lists of 0/1
             (care 0 = don't care).
    n_gates: exact number of gates to use.
    rng: if given, randomize solver phases so repeated calls yield varied solutions.
    forbid: list of previous structure-literal sets (from the second return slot of
            solutions found with collect_structure=True via `last_structure`) -- kept
            simple: each entry is an iterable of positive literals to block jointly.
    sym_break: add no-dangling-gate clauses (safe when scanning N ranges: a solution
               with a dead gate implies a smaller solution at an N already tested).
    allow_const_outputs: outputs may select constant 0/1, decoded as 'CONST0'/'CONST1'.
    status_out: optional dict; gets status_out['status'] = 'SAT' | 'UNSAT' | 'UNKNOWN'
                ('UNKNOWN' = conflict budget exhausted, no verdict).
    Returns (gates, out_sel) or None.  gates: list of (op, fanin1, fanin2) with
    fanin indices: 0..NI-1 = block inputs, NI+i = gate i.  out_sel: per output a
    signal index, or the string 'CONST0'/'CONST1' when allow_const_outputs.
    """
    R = len(input_rows)
    NI = len(input_rows[0])
    N = n_gates
    pool = IDPool()
    cls = []

    def sv(i, j, k):  # gate i selects fanins (j, k), j<k or (j,j) for NOT-style
        return pool.id(('s', i, j, k))

    def ov(i, o):     # op selector: gate i has op index o
        return pool.id(('o', i, o))

    def val(i, r):    # value of gate i on row r
        return pool.id(('v', i, r))

    def inval(j, r):
        return 1 if input_rows[r][j] else 0  # constant truth (handled inline)

    def outv(t, x):   # output t selects signal x (0..NI+N-1)
        return pool.id(('t', t, x))

    nsig = NI + N

    # each gate: exactly one fanin pair, exactly one op
    for i in range(N):
        pairs = []
        for j in range(NI + i):
            for k in range(j, NI + i):
                pairs.append(sv(i, j, k))
        cls.append(pairs)
        for a in range(len(pairs)):
            for b in range(a + 1, len(pairs)):
                cls.append([-pairs[a], -pairs[b]])
        ops = [ov(i, o) for o in range(4)]
        cls.append(ops)
        for a in range(4):
            for b in range(a + 1, 4):
                cls.append([-ops[a], -ops[b]])
        # NOT uses pair (j,j); binary ops use j<k
        for j in range(NI + i):
            cls.append([-sv(i, j, j), ov(i, 3)])
            for k in range(j + 1, NI + i):
                cls.append([-sv(i, j, k), -ov(i, 3)])

    def sigval(x, r):
        """Return literal or constant for signal x on row r: ('const', c) or lit."""
        if x < NI:
            return ('const', inval(x, r))
        return val(x - NI, r)

    # semantics
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
                        # value of op(a,b) on row r as clauses
                        # handle constants by simplification
                        def lit_or_none(x):
                            return None if isinstance(x, tuple) else x
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
                            elif opname == 'XOR':
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
                            elif opname == 'XOR':
                                cls.append([-s, -olit, v, a, -b])
                                cls.append([-s, -olit, v, -a, b])
                                cls.append([-s, -olit, -v, a, b])
                                cls.append([-s, -olit, -v, -a, -b])

    # outputs: select one signal each; match spec on care rows
    NT = len(targets)
    nout_sel = nsig + (2 if allow_const_outputs else 0)  # nsig -> CONST0, nsig+1 -> CONST1
    for t, (spec, care) in enumerate(targets):
        sel = [outv(t, x) for x in range(nout_sel)]
        cls.append(sel)
        for r in range(R):
            if not care[r]:
                continue
            want = spec[r]
            for x in range(nsig):
                a = sigval(x, r)
                if isinstance(a, tuple):
                    if a[1] != want:
                        cls.append([-outv(t, x)])
                else:
                    cls.append([-outv(t, x), a if want else -a])
            if allow_const_outputs:
                if want != 0:
                    cls.append([-outv(t, nsig)])
                if want != 1:
                    cls.append([-outv(t, nsig + 1)])

    # symmetry breaking: every gate must feed a later gate or an output
    if sym_break:
        for i in range(N):
            users = []
            for i2 in range(i + 1, N):
                for j in range(NI + i2):
                    for k in range(j, NI + i2):
                        if j == NI + i or k == NI + i:
                            users.append(sv(i2, j, k))
            for t in range(NT):
                users.append(outv(t, NI + i))
            cls.append(users)

    # block previously seen structures (for solution enumeration / plateau moves)
    if forbid:
        for lits in forbid:
            cls.append([-l for l in lits])

    with Cadical195(bootstrap_with=cls) as S:
        phases = []
        if rng is not None:
            for i in range(N):
                for j in range(NI + i):
                    for k in range(j, NI + i):
                        v = sv(i, j, k)
                        phases.append(v if rng.random() < 0.5 else -v)
                for o in range(4):
                    v = ov(i, o)
                    phases.append(v if rng.random() < 0.5 else -v)
        if hint is not None:
            # warm-start from a known (usually N+1-gate) solution: bias gate i
            # toward the hint's gate i structure (later entries win)
            hgates, houts = hint
            for i, (op, j, k) in enumerate(hgates[:N]):
                if k < NI + i and j <= k:
                    phases.append(sv(i, j, k))
                    phases.append(ov(i, OPS.index(op)))
            for t, x in enumerate(houts):
                if t < NT and isinstance(x, int) and x < NI + N:
                    phases.append(outv(t, x))
        if phases:
            S.set_phases(phases)
        if solver_time:
            S.conf_budget(int(solver_time))
            r = S.solve_limited()
            if r is not True:
                if status_out is not None:
                    status_out['status'] = 'UNSAT' if r is False else 'UNKNOWN'
                return None
        elif not S.solve():
            if status_out is not None:
                status_out['status'] = 'UNSAT'
            return None
        model = set(l for l in S.get_model() if l > 0)
    if status_out is not None:
        status_out['status'] = 'SAT'

    gates = []
    struct = []
    for i in range(N):
        op = next(o for o in range(4) if ov(i, o) in model)
        pr = next((j, k) for j in range(NI + i) for k in range(j, NI + i)
                  if sv(i, j, k) in model)
        gates.append((OPS[op], pr[0], pr[1]))
        struct.append(sv(i, pr[0], pr[1]))
        struct.append(ov(i, op))
    outs = []
    for t in range(NT):
        x = next(x for x in range(nout_sel) if outv(t, x) in model)
        if allow_const_outputs and x >= nsig:
            outs.append('CONST0' if x == nsig else 'CONST1')
        else:
            outs.append(x)
        struct.append(outv(t, x))
    if status_out is not None:
        status_out['structure'] = struct
    return gates, outs


def synth_cegar(input_rows, targets, n_gates, conf_budget=500000, max_iters=60,
                rng=None, forbid=None, sym_break=True, allow_const_outputs=False,
                status_out=None, hint=None):
    """CEGAR variant: constrain on a growing subset of rows; verify candidates
    on all rows and refine.  UNSAT on a subset is UNSAT overall."""
    R = len(input_rows)
    if R == 0:
        return None
    # start with a small diverse subset
    active = list(range(0, R, max(1, R // 8)))[:8]
    active_set = set(active)
    it = 0
    while it < max_iters:
        it += 1
        rows_sub = [input_rows[r] for r in active]
        targs_sub = [([spec[r] for r in active], [care[r] for r in active])
                     for (spec, care) in targets]
        res = synth(rows_sub, targs_sub, n_gates, solver_time=conf_budget,
                    rng=rng, forbid=forbid, sym_break=sym_break,
                    allow_const_outputs=allow_const_outputs, status_out=status_out,
                    hint=hint)
        if res is None:
            return None
        gates, outs = res
        # simulate candidate on all rows
        bad = None
        for r in range(R):
            if r in active_set:
                continue
            vals = list(input_rows[r])
            for (op, j, k) in gates:
                if op == 'NOT':
                    vals.append(1 - vals[j])
                elif op == 'AND':
                    vals.append(vals[j] & vals[k])
                elif op == 'OR':
                    vals.append(vals[j] | vals[k])
                else:
                    vals.append(vals[j] ^ vals[k])
            for t, (spec, care) in enumerate(targets):
                if not care[r]:
                    continue
                got = (0 if outs[t] == 'CONST0' else 1 if outs[t] == 'CONST1'
                       else vals[outs[t]])
                if got != spec[r]:
                    bad = r
                    break
            if bad is not None:
                break
        if bad is None:
            return gates, outs
        active.append(bad)
        active_set.add(bad)
    if status_out is not None:
        status_out['status'] = 'UNKNOWN'  # ran out of CEGAR iterations
    return None


def synth_min(input_rows, targets, lo=0, hi=30, verbose=True):
    """Find minimal gate count by increasing N; returns (n, gates, outs)."""
    for n in range(lo, hi + 1):
        res = synth(input_rows, targets, n)
        if verbose:
            print(f'  N={n}: {"SAT" if res else "UNSAT"}', flush=True)
        if res:
            return (n,) + res
    return None
