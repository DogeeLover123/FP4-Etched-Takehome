"""Harness for the optimizer pipeline in this folder.

Trimmed copy of the reference project's harness.py: only what optimizer.py,
window_sat.py, sat_synth.py, ils.py, lb_sat.py, remap_variants.py, and
baseline.py actually import. Dropped: PLA/BLIF export, the ABC integration
class -- none of the scripts here depend on an external synthesis tool.

Conventions (same as the top-level repo's harness.py):
- FP4 values are represented in *halves* (v2 = 2*value), all ints.
- A remap is a tuple of 16 ints: remap[code] = v2 value for that 4-bit code.
  Valid remaps are permutations of the multiset {0,0, +-1,+-2,+-3,+-4,+-6,+-8,+-12}.
- Netlist: inputs 'a0'..'a3' (a0 = LSB of A's code), 'b0'..'b3'; gates are
  (out_name, op, in_names...) with op in {AND, OR, XOR, NOT}; outputs is a
  list of 9 signal names, index 0 = LSB of the result. 'CONST0'/'CONST1' are
  free constants.
- Bit-parallel simulation: each signal is a 256-bit int, bit idx = a*16+b.
"""

HALF_VALUES = (0, 0, 1, -1, 2, -2, 3, -3, 4, -4, 6, -6, 8, -8, 12, -12)

# Original (PDF) mapping code -> v2, used by remap_variants.py as one of the
# raced alternatives.
PDF_REMAP = (0, 1, 2, 3, 4, 6, 8, 12, 0, -1, -2, -3, -4, -6, -8, -12)

MASK256 = (1 << 256) - 1


def is_valid_remap(remap):
    return sorted(remap) == sorted(HALF_VALUES)


def spec_bits(remap):
    """9 ints (256-bit); bit idx=a*16+b of specs[j] = output bit j for (a,b)."""
    specs = [0] * 9
    for a in range(16):
        for b in range(16):
            idx = a * 16 + b
            prod = (remap[a] * remap[b]) & 511
            for j in range(9):
                if (prod >> j) & 1:
                    specs[j] |= 1 << idx
    return specs


def input_bits():
    """256-bit patterns for the 8 input signals."""
    sig = {}
    for i in range(4):
        pa = pb = 0
        for a in range(16):
            for b in range(16):
                idx = a * 16 + b
                if (a >> i) & 1:
                    pa |= 1 << idx
                if (b >> i) & 1:
                    pb |= 1 << idx
        sig[f'a{i}'] = pa
        sig[f'b{i}'] = pb
    return sig


class SimError(Exception):
    pass


def simulate(gates, outputs):
    sig = input_bits()
    sig['CONST0'] = 0
    sig['CONST1'] = MASK256
    try:
        return _simulate(sig, gates, outputs)
    except KeyError as e:
        raise SimError(str(e))


def _simulate(sig, gates, outputs):
    for g in gates:
        name, op = g[0], g[1]
        ins = [sig[x] for x in g[2:]]
        if op == 'AND':
            sig[name] = ins[0] & ins[1]
        elif op == 'OR':
            sig[name] = ins[0] | ins[1]
        elif op == 'XOR':
            sig[name] = ins[0] ^ ins[1]
        elif op == 'NOT':
            sig[name] = ~ins[0] & MASK256
        elif op == 'BUF':
            sig[name] = ins[0]
        else:
            raise ValueError(f'bad op {op}')
    return [sig[o] for o in outputs]


def gate_count(gates):
    return sum(1 for g in gates if g[1] != 'BUF')


def verify(remap, gates, outputs, verbose=False):
    assert is_valid_remap(remap), 'invalid remap'
    try:
        got = simulate(gates, outputs)
    except SimError:
        return False
    want = spec_bits(remap)
    ok = got == want
    if verbose and not ok:
        for a in range(16):
            for b in range(16):
                idx = a * 16 + b
                g = sum(((got[j] >> idx) & 1) << j for j in range(9))
                w = sum(((want[j] >> idx) & 1) << j for j in range(9))
                if g != w:
                    print(f'MISMATCH a={a:04b}({remap[a]/2}) b={b:04b}({remap[b]/2}): '
                          f'got {g:09b} want {w:09b}')
    return ok


class Builder:
    """Tiny DSL for hand-writing netlists (used by baseline.py)."""
    def __init__(self):
        self.gates = []
        self.n = 0

    def _new(self, op, *ins):
        if op == 'NOT':
            (x,) = ins
            if x == 'CONST0':
                return 'CONST1'
            if x == 'CONST1':
                return 'CONST0'
        else:
            x, y = ins
            if op == 'AND':
                if 'CONST0' in ins:
                    return 'CONST0'
                if x == 'CONST1':
                    return y
                if y == 'CONST1':
                    return x
                if x == y:
                    return x
            if op == 'OR':
                if 'CONST1' in ins:
                    return 'CONST1'
                if x == 'CONST0':
                    return y
                if y == 'CONST0':
                    return x
                if x == y:
                    return x
            if op == 'XOR':
                if x == 'CONST0':
                    return y
                if y == 'CONST0':
                    return x
                if x == y:
                    return 'CONST0'
                if x == 'CONST1':
                    return self._new('NOT', y)
                if y == 'CONST1':
                    return self._new('NOT', x)
        self.n += 1
        name = f'n{self.n}'
        self.gates.append((name, op) + ins)
        return name

    def AND(self, x, y):
        return self._new('AND', x, y)

    def OR(self, x, y):
        return self._new('OR', x, y)

    def XOR(self, x, y):
        return self._new('XOR', x, y)

    def NOT(self, x):
        return self._new('NOT', x)
