"""Custom netlist optimizer for the exact cost model (AND/OR/XOR/NOT each = 1).

Greedy don't-care-aware resubstitution + MFFC accounting, with random
perturbation kicks for iterated local search. This is "pass 1" in the
README's methodology description (78 -> 73), and also the local-descent
step used after every window-SAT splice (window_sat.py) and after every
perturbation (ils.py).
"""
import random
from harness import input_bits, spec_bits, MASK256, gate_count

INPUTS = ('a0', 'a1', 'a2', 'a3', 'b0', 'b1', 'b2', 'b3')


def apply_op(op, ins):
    if op == 'AND':
        return ins[0] & ins[1]
    if op == 'OR':
        return ins[0] | ins[1]
    if op == 'XOR':
        return ins[0] ^ ins[1]
    if op == 'NOT':
        return ~ins[0] & MASK256
    if op == 'BUF':
        return ins[0]
    raise ValueError(op)


class Net:
    def __init__(self, gates, outputs, specs):
        # gates: list of (name, op, *ins); must be topologically ordered.
        # Canonicalize names through the global fresh counter to prevent
        # collisions with names minted later.
        ren = {}
        canon = []
        for g in gates:
            n = fresh()
            ren[g[0]] = n
            canon.append((n, g[1]) + tuple(ren.get(x, x) for x in g[2:]))
        self.gates = canon
        self.outputs = [ren.get(o, o) for o in outputs]
        self.specs = specs  # list of 9 ints
        self.base = dict(input_bits())
        self.base['CONST0'] = 0
        self.base['CONST1'] = MASK256
        self.resim()

    def resim(self):
        self.val = dict(self.base)
        for g in self.gates:
            self.val[g[0]] = apply_op(g[1], [self.val[x] for x in g[2:]])

    def out_vals(self):
        return [self.val[o] for o in self.outputs]

    def check(self):
        return self.out_vals() == self.specs

    def gate_index(self):
        return {g[0]: i for i, g in enumerate(self.gates)}

    def fanout_cone(self, w):
        """Names of gates (transitively) depending on w."""
        cone = {w}
        for g in self.gates:
            if any(x in cone for x in g[2:]):
                cone.add(g[0])
        return cone

    def care(self, w):
        """256-bit mask of patterns where flipping w changes some output."""
        cone = self.fanout_cone(w)
        v = dict(self.val)
        v[w] = ~self.val[w] & MASK256
        for g in self.gates:
            if g[0] in cone and g[0] != w:
                v[g[0]] = apply_op(g[1], [v[x] for x in g[2:]])
        diff = 0
        for j, o in enumerate(self.outputs):
            diff |= v[o] ^ self.val[o]
        return diff

    def refcounts(self):
        rc = {}
        for g in self.gates:
            for x in g[2:]:
                rc[x] = rc.get(x, 0) + 1
        for o in self.outputs:
            rc[o] = rc.get(o, 0) + 1
        return rc

    def mffc(self, w, gidx=None):
        """Set of gate names removable if w were replaced by a fresh signal."""
        gidx = gidx or self.gate_index()
        if w not in gidx:
            return set()
        rc = self.refcounts()
        removed = set()
        stack = [w]
        rc[w] = 0
        while stack:
            n = stack.pop()
            if n in gidx and rc.get(n, 0) == 0 and n not in removed:
                removed.add(n)
                for x in self.gates[gidx[n]][2:]:
                    if x in gidx:
                        rc[x] -= 1
                        if rc[x] == 0:
                            stack.append(x)
        return removed

    def replace(self, w, new_gates, final):
        """Replace signal w by `final` (with new_gates appended; list re-topo-sorted)."""
        gidx = self.gate_index()
        # protect signals referenced by the replacement from MFFC removal
        protected = {final}
        for g in new_gates:
            protected.update(g[2:])
        rc = self.refcounts()
        removed = set()
        stack = [w]
        rc[w] = 0
        while stack:
            n = stack.pop()
            if n in gidx and rc.get(n, 0) == 0 and n not in removed and n not in protected:
                removed.add(n)
                for x in self.gates[gidx[n]][2:]:
                    if x in gidx:
                        rc[x] -= 1
                        if rc[x] == 0:
                            stack.append(x)
        out = [g for g in self.gates if g[0] not in removed] + list(new_gates)
        def ren(x):
            return final if x == w else x
        self.gates = [(g[0], g[1]) + tuple(ren(x) for x in g[2:]) for g in out]
        self.outputs = [ren(o) for o in self.outputs]
        self.toposort()
        self.dedupe()
        self.resim()

    def toposort(self):
        defs = {g[0]: g for g in self.gates}
        placed = set(self.base)
        order = []
        temp = set()

        def visit(n):
            if n in placed or n not in defs:
                return
            if n in temp:
                raise RuntimeError(f'cycle at {n}')
            temp.add(n)
            for x in defs[n][2:]:
                visit(x)
            temp.discard(n)
            placed.add(n)
            order.append(defs[n])

        import sys
        old = sys.getrecursionlimit()
        sys.setrecursionlimit(100000)
        try:
            for g in self.gates:
                visit(g[0])
        finally:
            sys.setrecursionlimit(old)
        self.gates = order

    def dedupe(self):
        """Merge structurally identical gates; drop dead gates; fold constants."""
        changed = True
        while changed:
            changed = False
            seen = {}
            ren = {}
            out = []
            for g in self.gates:
                ins = tuple(ren.get(x, x) for x in g[2:])
                op = g[1]
                # normalize commutative input order
                if op != 'NOT' and op != 'BUF':
                    ins = tuple(sorted(ins))
                # constant folding / identities
                tgt = None
                if op == 'NOT':
                    if ins[0] == 'CONST0': tgt = 'CONST1'
                    elif ins[0] == 'CONST1': tgt = 'CONST0'
                elif op == 'BUF':
                    tgt = ins[0]
                elif ins[0] == ins[1]:
                    tgt = ins[0] if op != 'XOR' else 'CONST0'
                elif op == 'AND':
                    if 'CONST0' in ins: tgt = 'CONST0'
                    elif ins[0] == 'CONST1': tgt = ins[1]
                    elif ins[1] == 'CONST1': tgt = ins[0]
                elif op == 'OR':
                    if 'CONST1' in ins: tgt = 'CONST1'
                    elif ins[0] == 'CONST0': tgt = ins[1]
                    elif ins[1] == 'CONST0': tgt = ins[0]
                elif op == 'XOR':
                    if ins[0] == 'CONST0': tgt = ins[1]
                    elif ins[1] == 'CONST0': tgt = ins[0]
                if tgt is not None:
                    ren[g[0]] = tgt
                    changed = True
                    continue
                key = (op, ins)
                if key in seen:
                    ren[g[0]] = seen[key]
                    changed = True
                else:
                    seen[key] = g[0]
                    out.append((g[0], op) + ins)
            self.gates = out
            def follow(x):
                while x in ren:
                    x = ren[x]
                return x
            self.outputs = [follow(o) for o in self.outputs]
        # dead code elimination
        live = set(self.outputs)
        for g in reversed(self.gates):
            if g[0] in live:
                live.update(g[2:])
        self.gates = [g for g in self.gates if g[0] in live]
        self.resim()

    def count(self):
        return sum(1 for g in self.gates if g[1] != 'BUF')


def signals_list(net):
    return list(INPUTS) + ['CONST0', 'CONST1'] + [g[0] for g in net.gates]


FRESH = [0]


def fresh():
    FRESH[0] += 1
    return f'r{FRESH[0]}'


def try_resub(net, w, max_new=2, window=26):
    """Try to re-express w with <= max_new new gates for positive gain."""
    gidx = net.gate_index()
    if w not in gidx:
        return False
    saving = len(net.mffc(w, gidx))
    if saving <= 0:
        return False
    care = net.care(w)
    if care == 0:
        net.replace(w, [], 'CONST0')
        return True
    wv = net.val[w]
    cone = net.fanout_cone(w)
    cands = [s for s in signals_list(net) if s not in cone and s != w]
    # constants
    if (wv & care) == 0:
        net.replace(w, [], 'CONST0')
        return True
    if (~wv & care & MASK256) == 0:
        net.replace(w, [], 'CONST1')
        return True
    # 0-resub: w == x
    for x in cands:
        if ((net.val[x] ^ wv) & care) == 0:
            net.replace(w, [], x)
            return True
    # 1-resub (needs saving >= 2)
    if saving >= 2:
        for x in cands:
            if ((~net.val[x] ^ wv) & care & MASK256) == 0:
                n = fresh()
                net.replace(w, [(n, 'NOT', x)], n)
                return True
        vals = [(x, net.val[x]) for x in cands]
        for i in range(len(vals)):
            x, xv = vals[i]
            for k in range(i + 1, len(vals)):
                y, yv = vals[k]
                for op, r in (('AND', xv & yv), ('OR', xv | yv), ('XOR', xv ^ yv)):
                    if ((r ^ wv) & care) == 0:
                        n = fresh()
                        net.replace(w, [(n, op, x, y)], n)
                        return True
    # 2-resub (needs saving >= 3), windowed candidates
    if saving >= 3 and max_new >= 2:
        near = window_signals(net, w, window, cone)
        vals = [(x, net.val[x]) for x in near]
        L = len(vals)
        for i in range(L):
            x, xv = vals[i]
            nxv = ~xv & MASK256
            for k in range(L):
                y, yv = vals[k]
                for m in range(k + 1, L):
                    z, zv = vals[m]
                    for hop, hv in (('AND', yv & zv), ('OR', yv | zv), ('XOR', yv ^ zv)):
                        for gop, gv in (('AND', xv & hv), ('OR', xv | hv), ('XOR', xv ^ hv)):
                            if ((gv ^ wv) & care) == 0:
                                h = fresh(); n = fresh()
                                net.replace(w, [(h, hop, y, z), (n, gop, x, h)], n)
                                return True
    return False


def window_signals(net, w, cap, cone):
    """Signals structurally near w (fanins of cone gates, their fanins, inputs)."""
    gidx = net.gate_index()
    near = []
    seen = set()
    frontier = set()
    for g in net.gates:
        if g[0] in cone:
            frontier.update(g[2:])
    for _ in range(2):
        nxt = set()
        for x in frontier:
            if x in seen or x in cone:
                continue
            seen.add(x)
            near.append(x)
            if x in gidx:
                nxt.update(net.gates[gidx[x]][2:])
        frontier = nxt
    for x in INPUTS:
        if x not in seen:
            near.append(x)
            seen.add(x)
    return near[:cap]


def optimize(net, passes=50):
    improved = True
    p = 0
    while improved and p < passes:
        improved = False
        p += 1
        for g in list(net.gates):
            w = g[0]
            if try_resub(net, w):
                assert net.check(), 'broke function!'
                improved = True
    return net


def perturb(net, rng):
    """Random function-preserving expansion to escape local minima."""
    g = rng.choice(net.gates)
    w, op = g[0], g[1]
    ins = g[2:]
    n1, n2, n3 = fresh(), fresh(), fresh()
    repl = None
    if op == 'AND':
        repl = [(n1, 'NOT', ins[0]), (n2, 'NOT', ins[1]), (n3, 'OR', n1, n2), (w, 'NOT', n3)]
    elif op == 'OR':
        repl = [(n1, 'NOT', ins[0]), (n2, 'NOT', ins[1]), (n3, 'AND', n1, n2), (w, 'NOT', n3)]
    elif op == 'XOR':
        which = rng.random()
        if which < 0.5:
            repl = [(n1, 'OR', ins[0], ins[1]), (n2, 'AND', ins[0], ins[1]),
                    (n3, 'NOT', n2), (w, 'AND', n1, n3)]
        else:
            repl = [(n1, 'AND', ins[0], ins[1]), (n2, 'OR', ins[0], ins[1]),
                    (n3, 'NOT', n1), (w, 'AND', n2, n3)]
    elif op == 'NOT':
        return
    gidx = net.gate_index()
    pos = gidx[w]
    net.gates = net.gates[:pos] + repl + net.gates[pos + 1:]
    net.resim()
