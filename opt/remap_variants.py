"""Remap-variant search: translation-layer splice + optimization race.

This is the source of the README's remap-race claim (33 alternative
encodings, none beating 62; best seen was 64 under a fixed per-candidate
budget). For candidate remap R2, build T = R1^-1 . R2 (new code
-> old code preserving value), synthesize T minimally with SAT, prepend to
the current best netlist for both inputs, then optimize. Score = optimized
gate count.

Usage: python3 remap_variants.py <shard> <nshards> [opt_seconds]
Splits the candidate list across `nshards` shards so this can be run in
parallel; shard 0 of 1 runs everything in one process.
"""
import json, random, sys, time
from harness import spec_bits, is_valid_remap
from optimizer import Net, optimize, fresh, INPUTS
from window_sat import attempt
from sat_synth import synth
from abc_flow import remap_sme


def make_translation(r_old, r_new):
    """T[new_code] = old_code with same value (zeros matched arbitrarily)."""
    old_codes = {}
    for c, v in enumerate(r_old):
        old_codes.setdefault(v, []).append(c)
    T = [None] * 16
    used = {v: 0 for v in old_codes}
    for c, v in enumerate(r_new):
        T[c] = old_codes[v][used[v] % len(old_codes[v])]
        used[v] += 1
    return T


def synth_translation(T, max_gates=10, budget=300000):
    rows = [tuple((c >> i) & 1 for i in range(4)) for c in range(16)]
    targets = []
    for bit in range(4):
        spec = [(T[c] >> bit) & 1 for c in range(16)]
        targets.append((spec, [1] * 16))
    for n in range(0, max_gates + 1):
        res = synth(rows, targets, n, solver_time=budget)
        if res:
            return n, res[0], res[1]
    return None


def spliced_net(base_gates, base_outputs, tgates, touts, r_new):
    """Prepend translation for inputs a and b; rename base inputs."""
    import re
    from optimizer import FRESH
    mx = 0
    for g in base_gates:
        m = re.fullmatch(r'r(\d+)', g[0])
        if m:
            mx = max(mx, int(m.group(1)))
    FRESH[0] = max(FRESH[0], mx + 1)
    gates = []
    ren = {}
    for pref in ('a', 'b'):
        names = [f'{pref}{i}' for i in range(4)]
        for (op, j, k) in tgates:
            n = fresh()
            if op == 'NOT':
                gates.append((n, 'NOT', names[j]))
            else:
                gates.append((n, op, names[j], names[k]))
            names.append(n)
        for bit in range(4):
            x = touts[bit]
            ren[f'{pref}{bit}'] = names[x]
    body = []
    for g in base_gates:
        body.append((g[0], g[1]) + tuple(ren.get(x, x) for x in g[2:]))
    return gates + body, [ren.get(o, o) for o in base_outputs]


def score_variant(name, r_new, base, opt_seconds, rng):
    r_old = tuple(base['remap'])
    T = make_translation(r_old, r_new)
    tr = synth_translation(T)
    if tr is None:
        print(f'{name}: translation synth failed', flush=True)
        return None
    tn, tgates, touts = tr
    gates, outputs = spliced_net([tuple(g) for g in base['gates']],
                                 base['outputs'], tgates, touts, r_new)
    specs = spec_bits(r_new)
    net = Net(gates, outputs, specs)
    if not net.check():
        print(f'{name}: splice INCORRECT', flush=True)
        return None
    optimize(net)
    t0 = time.time()
    best = (net.count(), list(net.gates), list(net.outputs))
    while time.time() - t0 < opt_seconds:
        try:
            if rng.random() < 0.6:
                if attempt(net, rng, max_gates=rng.choice([7, 8, 9]),
                           max_inputs=rng.choice([6, 7, 8])):
                    optimize(net)
            else:
                from optimizer import perturb
                for _ in range(rng.randint(1, 3)):
                    perturb(net, rng)
                optimize(net)
            if not net.check():
                raise ValueError
        except Exception:
            net = Net(best[1], best[2], specs)
            continue
        if net.count() < best[0]:
            best = (net.count(), list(net.gates), list(net.outputs))
        elif net.count() > best[0] + 6:
            net = Net(best[1], best[2], specs)
    print(f'{name}: T={tn}g -> optimized {best[0]}', flush=True)
    return best[0], r_new, best[1], best[2]


def candidates():
    """Generate (name, remap) candidates as tweaks of the (s,m,e) scheme."""
    out = []

    def build(exp_perm, zero_slot, mag_swap=None):
        remap = []
        for code in range(16):
            s, m, e_code = (code >> 3) & 1, (code >> 2) & 1, code & 3
            e = exp_perm[e_code]
            if m == 1 and e == zero_slot:
                v = 0
            else:
                # mantissa-3 magnitudes occupy the three non-zero_slot exponents
                if m == 1:
                    es = [x for x in range(4) if x != zero_slot]
                    v = 3 << es.index(e) if e in es else None
                else:
                    v = 1 << e
                if s:
                    v = -v
            remap.append(v)
        if mag_swap:
            a, b = mag_swap
            remap = [(-b if v == -a else -a if v == -b else
                      b if v == a else a if v == b else v) for v in remap]
        return tuple(remap)

    import itertools
    perms = list(itertools.permutations(range(4)))
    # exponent code permutations (identity mantissa layout, zero at e=3)
    for p in [(0, 1, 2, 3), (0, 1, 3, 2), (1, 0, 2, 3), (3, 2, 1, 0),
              (0, 2, 1, 3), (2, 3, 0, 1), (0, 3, 1, 2), (1, 2, 0, 3)]:
        out.append((f'expperm{p}', build(p, 3)))
    # zero slot variants
    for zs in (0, 1, 2):
        out.append((f'zeroslot{zs}', build((0, 1, 2, 3), zs)))
    # magnitude swaps (non-affine tweaks)
    mags = [1, 2, 3, 4, 6, 8, 12]
    for a, b in itertools.combinations(mags, 2):
        out.append((f'swap{a}_{b}', build((0, 1, 2, 3), 3, (a, b))))
    # PDF original
    from harness import PDF_REMAP
    out.append(('pdf', PDF_REMAP))
    seen = set()
    uniq = []
    for name, r in out:
        if r in seen or not is_valid_remap(r):
            continue
        seen.add(r)
        uniq.append((name, r))
    return uniq


if __name__ == '__main__':
    shard = int(sys.argv[1])
    nshards = int(sys.argv[2])
    opt_seconds = float(sys.argv[3]) if len(sys.argv) > 3 else 180
    base = json.load(open('best62.json'))
    rng = random.Random(1000 + shard)
    results = []
    for i, (name, r) in enumerate(candidates()):
        if i % nshards != shard:
            continue
        res = score_variant(name, r, base, opt_seconds, rng)
        if res:
            results.append((res[0], name, list(res[1]),
                            [list(g) for g in res[2]], res[3]))
    results.sort(key=lambda x: x[0])
    json.dump(results[:5], open(f'variants_{shard}.json', 'w'))
    print('BEST OF SHARD:', [(r[0], r[1]) for r in results[:5]])
