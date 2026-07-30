"""Window-based SAT resynthesis: replace small subcircuits with provably
smaller ones, using reachable-row don't-cares; global verification after splice.
This is "pass 2" in the README's methodology description (73 -> 62, the
workhorse -- almost all of the automated savings came from this pass).

Also: equal-size "plateau" moves -- replace a window with a *different*
same-size implementation (randomized SAT phases + tabu on a canonical net
signature) to random-walk the plateau of equal-cost circuits between descents."""
import hashlib, random
from optimizer import Net, apply_op, fresh, INPUTS
from harness import MASK256
from sat_synth import synth


def pick_window(net, rng, max_gates=9, max_inputs=7):
    """Random connected cone of gates. Returns (wgates:set of names) or None."""
    g0 = rng.choice(net.gates)[0]
    gidx = net.gate_index()
    W = {g0}
    frontier = [g0]
    while frontier and len(W) < max_gates:
        n = frontier.pop(rng.randrange(len(frontier)))
        g = net.gates[gidx[n]]
        cands = [x for x in g[2:] if x in gidx and x not in W]
        # also occasionally grow upward (fanouts)
        ups = [h[0] for h in net.gates
               if any(x in W for x in h[2:]) and h[0] not in W]
        pool = cands + (ups if rng.random() < 0.4 else [])
        rng.shuffle(pool)
        for c in pool:
            if len(W) >= max_gates:
                break
            W.add(c)
            frontier.append(c)
    # window inputs: signals used by W, defined outside W
    win = []
    for n in W:
        for x in net.gates[gidx[n]][2:]:
            if x not in W and x not in win:
                win.append(x)
    if len(win) > max_inputs:
        return None
    # window outputs: W-signals used outside W or primary outputs
    used_outside = set(net.outputs)
    for g in net.gates:
        if g[0] not in W:
            used_outside.update(g[2:])
    wout = [n for n in W if n in used_outside]
    return W, win, wout


def window_rows(net, win, wout):
    """Deduped rows over window inputs; per-row spec and care for each output."""
    cares = {o: net.care(o) for o in wout}
    rows = {}
    for p in range(256):
        key = tuple((net.val[x] >> p) & 1 for x in win)
        spec = tuple((net.val[o] >> p) & 1 for o in wout)
        care = tuple((cares[o] >> p) & 1 for o in wout)
        if key in rows:
            s2, c2 = rows[key]
            # merge: care OR; spec must agree where both care (it does by construction)
            rows[key] = (s2, tuple(a | b for a, b in zip(c2, care)))
        else:
            rows[key] = (spec, care)
    input_rows = list(rows.keys())
    targets = []
    for i, o in enumerate(wout):
        spec = [rows[r][0][i] for r in input_rows]
        care = [rows[r][1][i] for r in input_rows]
        targets.append((spec, care))
    return input_rows, targets


def net_signature(net):
    """Canonical, wiring-insensitive signature: sorted multiset of each gate's
    (op, 256-bit simulation vector).  Distinguishes functionally different
    plateau states while collapsing pure reorderings/renamings."""
    items = sorted((g[1], net.val[g[0]]) for g in net.gates)
    return hashlib.md5(repr(items).encode()).hexdigest()


def splice(net, W, win, wout, sgates, souts):
    """Splice a synthesized replacement for window W into net; True if the
    result still checks out (reverts on failure)."""
    names = list(win)
    new_gates = []
    for (op, j, k) in sgates:
        n = fresh()
        if op == 'NOT':
            new_gates.append((n, 'NOT', names[j]))
        else:
            new_gates.append((n, op, names[j], names[k]))
        names.append(n)
    ren = {}
    for o, x in zip(wout, souts):
        ren[o] = x if isinstance(x, str) else names[x]
    old_gates = list(net.gates)
    old_outputs = list(net.outputs)
    kept = [g for g in net.gates if g[0] not in W] + new_gates
    net.gates = [(g[0], g[1]) + tuple(ren.get(x, x) for x in g[2:]) for g in kept]
    net.outputs = [ren.get(o, o) for o in net.outputs]
    try:
        net.toposort()
        net.dedupe()
        ok = net.check()
    except Exception:
        ok = False
    if not ok:
        net.gates = old_gates
        net.outputs = old_outputs
        net.resim()
        return False
    return True


def attempt_equal(net, rng, tabu, max_gates=10, max_inputs=8, conf_budget=250000):
    """Equal-size window rewrite to a not-yet-seen plateau state.
    Returns 'moved' | 'shrunk' | False."""
    from sat_synth import synth_cegar
    pw = pick_window(net, rng, max_gates, max_inputs)
    if not pw:
        return False
    W, win, wout = pw
    if len(W) < 3:
        return False
    input_rows, targets = window_rows(net, win, wout)
    old_count = net.count()
    saved = (list(net.gates), list(net.outputs))
    res = synth_cegar(input_rows, targets, len(W), conf_budget=conf_budget,
                      rng=rng, allow_const_outputs=True)
    if res is None:
        return False
    if not splice(net, W, win, wout, *res):
        return False
    # dedupe may have shrunk the net: free win, accept unconditionally
    if net.count() < old_count:
        return 'shrunk'
    sig = net_signature(net)
    if sig in tabu:
        # already-visited state: revert so the walk doesn't cycle
        net.gates, net.outputs = saved
        net.resim()
        return False
    tabu.add(sig)
    return 'moved'


def attempt(net, rng, max_gates=9, max_inputs=7, specs=None):
    """One window resynthesis attempt. Returns True if net improved."""
    pw = pick_window(net, rng, max_gates, max_inputs)
    if not pw:
        return False
    W, win, wout = pw
    if len(W) <= 1:
        return False
    input_rows, targets = window_rows(net, win, wout)
    n_target = len(W) - 1
    # CEGAR keeps the row set small; cap only the structural size
    est = n_target * ((len(win) + n_target) ** 2 // 2) * min(len(input_rows), 24)
    if est > 1_200_000:
        return False
    from sat_synth import synth_cegar
    res = synth_cegar(input_rows, targets, n_target, conf_budget=400000,
                       allow_const_outputs=True)
    if res is None:
        return False
    # a success often means even fewer gates suffice; keep pushing down
    while n_target > 1:
        res2 = synth_cegar(input_rows, targets, n_target - 1,
                           conf_budget=400000, allow_const_outputs=True)
        if res2 is None:
            break
        res = res2
        n_target -= 1
    return splice(net, W, win, wout, *res)
