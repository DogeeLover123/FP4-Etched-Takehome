# optimizer

Runnable code behind the top-level README's "62 gates" and "why 62 is close
to the floor" claims. Start here if you want to see how the 78-gate hand
design (commit 2) actually got to 62 gates (commit 3), not just read about
it.

Everything here is self-contained (its own `harness.py`, no dependency on
the repo root) and was smoke-tested end to end while writing this, not just
copied in. Runs from within this directory: `cd opt && python3 <script>.py ...`

Requires the `python-sat` package (`pip install python-sat[pblib]`) for the
SAT-based pieces (`sat_synth.py`, `lb_sat.py`, and anything that imports
them). `baseline.py` and `optimizer.py` alone don't need it.

## the pipeline

1. **`baseline.py`** - the 78-gate hand design (same one described in the
   top-level README, built under this folder's own bit-order convention,
   `remap_sme()` in `abc_flow.py`). This is the optimizer's starting point.

       python3 baseline.py
       # baseline: 78 gates, verified=True

2. **`optimizer.py`** - don't-care-aware resubstitution. For every wire,
   compute its exact observability care set (flip it, see which of the 256
   input patterns change an output), then try to re-express it as a cheaper
   function of any other existing signal. This is "pass 1" in the top-level
   README: 78 -> 73.

       python3 -c "
       from harness import spec_bits; from abc_flow import remap_sme
       from baseline import build_baseline; from optimizer import Net, optimize
       net = Net(*build_baseline(), spec_bits(remap_sme()))
       optimize(net)
       print(net.count(), net.check())"
       # 73 True

3. **`window_sat.py`** + **`sat_synth.py`** - window SAT resynthesis, the
   workhorse pass (73 -> 62 in the original run). Repeatedly carves out a
   random 6-9 gate connected chunk, collects its actual reachable input
   rows and per-output care sets (both usually much smaller than the naive
   worst case), and asks a SAT solver (`sat_synth.synth`, exact Boolean-
   chain synthesis) for a strictly smaller circuit matching on the rows
   that matter. Splices in any improvement and re-verifies the whole
   circuit. `attempt()` is one such try; call it in a loop:

       python3 -c "
       import random
       from harness import spec_bits; from abc_flow import remap_sme
       from baseline import build_baseline; from optimizer import Net, optimize
       from window_sat import attempt
       net = Net(*build_baseline(), spec_bits(remap_sme())); optimize(net)
       rng = random.Random(0)
       for _ in range(300):
           if attempt(net, rng, max_gates=9, max_inputs=7):
               optimize(net)
       print(net.count(), net.check())"

   Reaching 62 from scratch this way takes real wall-clock time (the
   original run used multiple parallel workers over hours). A short smoke
   test (300 attempts, ~1-2 min) reliably gets partway (73 -> high 60s);
   `best62.json` below is the actual verified endpoint from the original
   run, included so you don't have to re-run hours of search just to see
   the final result or to use it as a starting point for the other tools.

4. **`ils.py`** - iterated local search, pass 3. When window-SAT stalls,
   deliberately inflate a random gate into an equivalent larger rewrite
   (`perturb` in `optimizer.py`) and re-descend, hoping to land in a
   different, smaller local optimum.

       python3 ils.py 0 60          # seed 0, 60 second budget
       python3 ils.py 0 60 best62.json ils_out.json   # resume from a checkpoint

5. **`lb_sat.py`** - the SAT lower-bound proofs. Two modes:
   - `fixed`: is there a circuit of <=N gates for *this specific* remap
     (loaded from `best62.json`)? UNSAT at N=14 is what proves the >=15
     floor cited in the top-level README.
   - `universal`: same question with the remap itself left as a free
     variable in the SAT formula, so UNSAT rules out *every* valid remap,
     not just this one. UNSAT at N=12 proves the >=13 floor.

         python3 lb_sat.py fixed 6 10        # small N, seconds
         python3 lb_sat.py universal 6 10    # small N, seconds to ~1 min

     Small N proves fast (this is what got smoke-tested: N=6 UNSAT for
     both modes, matching the original run's logs exactly). The actual
     N=14 fixed proof took ~2.4 hours and the N=12 universal proof took
     ~12 hours in the original run - reproducible, but budget for it.

6. **`remap_variants.py`** - the remap race. For each of 33 alternative
   encodings (every exponent-bit permutation, every zero placement,
   magnitude-code swaps, the spec's own default mapping), synthesizes a
   minimal *translation circuit* (new code -> old code, via SAT), splices
   it onto `best62.json`, and re-optimizes under a fixed per-candidate
   budget. No alternative tested beat 62; the best seen was 64.

       python3 remap_variants.py 0 1 30    # shard 0 of 1, 30s per candidate
       # e.g.: expperm(0, 1, 3, 2): T=1g -> optimized 64

     Smoke-tested on one candidate at 10s/attempt: scored 64 (worse than
     62, consistent with the top-level README's claim).

## what's not here

The reference project this was built from also has a much larger
supporting cast: a copy of Berkeley ABC's source (used once, to confirm
generic synthesis can't beat the hand design), a C++/mockturtle-based
optimizer, PLA/BLIF export for external tool interop, and dozens of
historical run logs and intermediate checkpoints from a multi-worker
parallel search. None of that is needed to reproduce the 78 -> 62 result or
the lower-bound proofs, so it isn't included here - this folder is the
actual working pipeline, not the full research trail.
