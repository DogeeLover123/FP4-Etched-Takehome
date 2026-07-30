"""Test harness for the Etched FP4 multiplier take-home.

Spec: given two 4-bit FP4 codes a, b, the circuit must output the 9-bit two's
complement integer equal to 4 * value(a) * value(b).

Internally, values are stored in *halves* (v2 = 2*value) so every FP4 value is
an integer, and the required output is simply v2(a) * v2(b), since
(2*va) * (2*vb) = 4*va*vb.

Conventions:
- ENCODING[code] = v2 value for that 4-bit code (standard FP4 here).
- Netlist: inputs 'a0'..'a3' (a0 = LSB of A's code), 'b0'..'b3'; gates are
  tuples (out_name, op, in_names...) with op in {AND, OR, XOR, NOT}; outputs
  is a list of 9 signal names, index 0 = LSB of the result.
  'CONST0'/'CONST1' are free constants.
- Simulation is bit-parallel: each signal is a 256-bit int, one bit per input
  pair (bit index = a*16 + b), so one pass simulates all cases at once.
"""

# Standard FP4 (E2M1) encoding, code bits (b3 b2 b1 b0) = (s, e1, e0, m):
#   e >= 1: value = (-1)^s * 1.m * 2^(e-1);   e = 0: subnormal (-1)^s * 0.m
# code -> 2*value:
STANDARD_FP4 = (0, 1, 2, 3, 4, 6, 8, 12, 0, -1, -2, -3, -4, -6, -8, -12)

# Remapped encoding, code bits (b3 b2 b1 b0) = (s, e1, e0, m) -- same bit
# order as standard FP4, only what the bits mean changes:
#   value = (-1)^s * (1 + 2m) * 2^(e-1), with (m=1, e=3) standing in for zero
#   (that (m,e) combo would be 3*2^3=24, which isn't a real fp4 magnitude, so
#   both signs of it are free to reuse as the two zero codes).
# code -> 2*value:
REMAP_FP4 = (1, 3, 2, 6, 4, 12, 8, 0, -1, -3, -2, -6, -4, -12, -8, 0)

MASK256 = (1 << 256) - 1


def spec_bits(encoding):
    """9 ints (256-bit each); bit a*16+b of specs[j] = output bit j for (a,b)."""
    specs = [0] * 9
    for a in range(16):
        for b in range(16):
            idx = a * 16 + b
            prod = (encoding[a] * encoding[b]) & 511
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


def simulate(gates, outputs):
    sig = input_bits()
    sig['CONST0'] = 0
    sig['CONST1'] = MASK256
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
        else:
            raise ValueError(f'bad op {op}')
    return [sig[o] for o in outputs]


def gate_count(gates):
    return len(gates)


def verify(encoding, gates, outputs, verbose=True):
    """Exhaustively check the netlist against the spec; True iff all 256 pass."""
    got = simulate(gates, outputs)
    want = spec_bits(encoding)
    if got == want:
        return True
    if verbose:
        for a in range(16):
            for b in range(16):
                idx = a * 16 + b
                g = sum(((got[j] >> idx) & 1) << j for j in range(9))
                w = sum(((want[j] >> idx) & 1) << j for j in range(9))
                if g != w:
                    print(f'MISMATCH a={a:04b}({encoding[a]/2}) '
                          f'b={b:04b}({encoding[b]/2}): got {g:09b} want {w:09b}')
    return False


class Builder:
    """Tiny DSL for writing netlists by hand."""

    def __init__(self):
        self.gates = []
        self.n = 0

    def _new(self, op, *ins):
        # trivial constant folding for convenience
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
