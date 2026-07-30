"""Iterated local search: perturb + resub-optimize, keeping the best netlist.

This is "pass 3" in the README's methodology description -- when window-SAT
resynthesis (window_sat.py) stalls, deliberately inflate a random gate with
an equivalent larger rewrite (perturb, in optimizer.py) and re-descend
(optimize), hoping to land in a different, smaller local optimum.

Usage: python3 ils.py <seed> <time_limit_seconds> [start.json] [out.json]
Starts from baseline.py's 78-gate hand design by default. Pass a prior
checkpoint (e.g. best62.json) as start_path to keep improving from there.
"""
import random, json, time, sys, os
from harness import spec_bits
from abc_flow import remap_sme
from baseline import build_baseline
from optimizer import Net, optimize, perturb


def load_start(path):
    if path and os.path.exists(path):
        d = json.load(open(path))
        return tuple(d['remap']), [tuple(g) for g in d['gates']], d['outputs']
    return None


def run(seed, time_limit, start_path=None, out_path=None):
    rng = random.Random(seed)
    st = load_start(start_path)
    if st:
        remap, gates, outputs = st
    else:
        remap = remap_sme()
        gates, outputs = build_baseline()
    specs = spec_bits(remap)
    net = Net(gates, outputs, specs)
    optimize(net)
    assert net.check()
    best = (net.count(), list(net.gates), list(net.outputs))
    print(f'[{seed}] start {best[0]}', flush=True)
    cur = net
    t0 = time.time()
    it = 0
    while time.time() - t0 < time_limit:
        it += 1
        try:
            for _ in range(rng.randint(1, 4)):
                perturb(cur, rng)
            optimize(cur)
            ok = cur.check()
        except (AssertionError, RuntimeError, KeyError):
            ok = False
        if not ok:
            cur = Net(best[1], best[2], specs)
            continue
        c = cur.count()
        if c <= best[0]:
            if c < best[0]:
                print(f'[{seed}] it {it}: new best {c}', flush=True)
                best = (c, list(cur.gates), list(cur.outputs))
                if out_path:
                    json.dump({'remap': list(remap), 'count': c,
                               'gates': [list(g) for g in best[1]],
                               'outputs': best[2]}, open(out_path, 'w'))
            else:
                best = (c, list(cur.gates), list(cur.outputs))
        elif rng.random() < 0.5:
            cur = Net(best[1], best[2], specs)
    print(f'[{seed}] done: {best[0]} after {it} iters', flush=True)
    if out_path:
        json.dump({'remap': list(remap), 'count': best[0],
                   'gates': [list(g) for g in best[1]],
                   'outputs': best[2]}, open(out_path, 'w'))
    return best


if __name__ == '__main__':
    seed = int(sys.argv[1])
    tl = float(sys.argv[2])
    start = sys.argv[3] if len(sys.argv) > 3 else None
    out = sys.argv[4] if len(sys.argv) > 4 else f'ils_best_{seed}.json'
    run(seed, tl, start, out)
