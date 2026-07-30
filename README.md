# FP4 multiplier

Final result: **62 gates** (33 AND, 18 XOR, 9 OR, 2 NOT), verified against
all 256 input pairs. This README covers the full design end to end, then
what changed in this last commit and why I belive 62 to be the effective minimum. Solution is in etched_fp4_multiplier_take_home_colab.py/fp4.py

NOTE: I have worked on this assignment across multiple commits. 

I added all of this to a Github because I think it would be interesting for you to see the progress made over time! I hope you have time to check out all the commits - every one of them has a separate README.md that explains the updates each commit has made.

fp4.sv is where I wrote the RTL implementation. I used it to write the overall design before
mapping it into raw logic gates. If you notice fp4.sv is unreadable now because this is after 
all the automatic optimizations. If you look through earlier commits though, fp4.sv will 
actually be readable haha. 

I started off with a naive floating point architecture, did some boolean optimization,
then applied the input mapping and then did a robust scripting optimization runs to drive to 62 gates.
The initial commits were almost entirely done manually by me, with the exception of actually mapping to logic gates as thats tedious, but I did use Claude in the last 2 commits to help, and for this commit Claude was responsiuble for setting up the automatic gate 
minimization - I just told it to verbosely scan the code to try to find any dont cares that can be optimized and told it to use some sort of SAT solver as I remember from my formal math class its used to prove if the optimized logic is still satisfiable 

## 1. the input remap

Standard FP4 (E2M1) encodes code bits as (s, e1, e0, m) with
value = 1.m * 2^(e-1) for e>=1, and a separate subnormal rule at e=0. That
subnormal special case, plus a real fractional significand, is what makes
the naive circuit expensive: you need to bump e=0 up to an "effective
exponent" of 1, and you need a real 2-bit x 2-bit significand multiplier.

Since the spec requires 4x the product anyway, double every operand instead
(fold the *4 into the representation instead of computing it separately).
Every FP4 magnitude, in halves, is one of {1,2,3,4,6,8,12} = {1,3}*2^{0..3},
except 3*2^3=24, which isn't a real value. That gap is exactly one code
point, and since the spec's signed zero is redundant (both zero codes mean
the same thing), it's a perfect fit for zero: no wasted encoding space.

Code bits stay (s, e1, e0, m) - same order as standard FP4, only the meaning
of m changes (mantissa is 1 or 3, not 1.m):

    value = (-1)^s * (1 + 2m) * 2^(e-1),  (m=1, e=3) -> 0

Written out (e = 2*e1 + e0; s flips the sign, so codes 0111 and 1111 both
decode to zero - that's the spec's redundant signed-zero pair):

| e (e1 e0) | m=0 | m=1 |
|-----------|-----|-----|
| 0 (00)    | 0.5 | 1.5 |
| 1 (01)    | 1   | 3   |
| 2 (10)    | 2   | 6   |
| 3 (11)    | 4   | 0   |

Both operands use this exact same mapping, as the spec requires. Interface,
concretely: a = {s, e1, e0, m} (a[3]=s ... a[0]=m), same for b, and the
output p is the 9-bit two's-complement integer 4\*va\*vb, p[0] = LSB,
p[8] = sign bit.

For nonzero operands this makes the whole multiply nearly free:

    4*va*vb = (-1)^(sa^sb) * 3^K * 2^E,  K = ma+mb in {0,1,2},  E = ea+eb in [0,6]

- **sign**: one XOR.
- **E**: a plain 2-bit + 2-bit adder, no bias correction. The "-1" in the
  value formula's 2^(e-1) and the spec's "*4" cancel exactly (each operand
  contributes 2^(e-1), two operands and the *4 give 2^(e-1)*2^(e-1)*4 =
  2^(e+e), no leftover term). e is used as a raw, un-biased exponent here,
  unlike standard FP4, so there's nothing to correct for.
- **K**: mantissa product 3^K in {1,3,9} = binary 1, 11, 1001. K only takes
  3 values, so this is a 4-bit constant pattern selected by 2 gates (K's
  own bits), not a real multiplier.
- **zero**: an operand is zero iff (m=1, e=3), a 3-input AND.

## 2. the thermometer trick

A naive implementation of the above still needs a barrel shifter (place the
3^K pattern at position E) and a separate two's complement negater (flip
and add 1 if the sign is negative). The negater alone was the single
biggest block in the design: flip 9 bits (9 gates) plus a 9-bit ripple-carry
"+1" (17 gates: each bit needs a sum XOR and a carry AND, except the top bit
which only needs the sum) = 26 gates. That "+1" is expensive because a
carry can ripple arbitrarily far - adding 1 to ...0111 has to flip every
trailing 1.

Flip-then-add-1 is mathematically the same as: find P's lowest set bit at
position E, leave everything below E at 0, leave bit E at 1, flip
everything above E. That's just a restatement of what the carry chain does
- it ripples through P's trailing zeros and stops the instant it hits the
lowest 1. Normally that restatement is useless, because finding the lowest
set bit at runtime costs as much as the carry chain did.

It's free here specifically because P isn't an arbitrary number: it's 3^K
(always odd, bit 0 always set) shifted left by E, so its lowest set bit is
*structurally* guaranteed to sit at E - nothing to search for. And E isn't
extra work either, it's the same value already needed to place P's bits in
the first place. So build a thermometer code of E, t_j = [E <= j], and one
chain does both jobs:

- **shift**: d_j = t_j ^ t_{j-1} is the one-hot decode of E - this IS the
  barrel shifter, no mux tree.
- **negate**: out_j = P_j ^ (s & t_{j-1}) is exactly "flip bits above E when
  negative" - the same chain, reused.

Zero gets cheaper as a side effect too: (m=1,e=3) forces E>=3, so the low
thermometer bits are already 0 on a zero operand without any special
casing.

Hand-built total after this trick: **78 gates**, verified.

## 3. this commit: automated gate minimization

Everything above is a hand design. This commit runs automated search on top
of it instead of hand-optimizing further, and ports whatever the search
found. No new circuit trick is being claimed here - the point of this
commit is that a general-purpose search, exploiting the fact that the whole
truth table is only 256 rows, can beat further hand tuning.

Two passes, run in sequence:

- **don't-care-aware resubstitution (78 -> 73)**: for every internal wire,
  flip it across all 256 input patterns and record which patterns change
  any output - that's the wire's exact observability care set, everywhere
  else its value doesn't matter. Try to re-express each wire as a cheaper
  function of any other existing signal, requiring agreement only on the
  care set, and keep it if it shrinks the circuit. This finds sharing the
  hand design missed.
- **window SAT resynthesis (73 -> 62)**: repeatedly carve out a small
  connected chunk of the circuit (6-12 gates, <=8 boundary inputs), collect
  its actual reachable input rows and each output's care set (both are
  usually much smaller than the naive 2^8), and ask a SAT solver for a
  strictly smaller circuit that matches on the rows that matter. Splice in
  any improvement and re-verify the whole thing against all 256 cases. This
  is where almost all of the remaining savings came from.

Both passes only ever accept a change after re-verifying the full circuit
against the exhaustive 256-case truth table, so correctness isn't in
question, only whether the search plateaued at the true minimum (see below).

The result is a flat, opaque chain of 62 gates with no recognizable
structure :)

## 4. why this design is close to optimal

The stronger part of this argument is architectural: why the design in
sections 1-2 doesn't leave gates on the table, before any automated search
even touches it. The automated-search evidence in section 3's methodology
backs that up empirically, but it's not the main reason to believe this.

### 4a. the architecture doesn't waste bits or gates

The remap uses every bit of information the code space has to offer. 16
codes exactly cover the 15 real values (7 positive magnitudes, 7 negative,
1 zero), with exactly one redundant code - and that redundancy is forced
by the spec itself (signed zero means two codes must mean the same thing),
not a slack left by this design. There's no unused encoding room left to
exploit further.

Given that tight encoding, each piece of the computation costs close to
what its actual information content demands, not more:

- **sign** needs the output to depend on both sa and sb - that's 1 gate,
  the minimum possible for a 2-input function that isn't a constant.
- **E** is a genuine sum of two 2-bit numbers, so real carry propagation is
  unavoidable - an adder-class circuit has to be there regardless of
  encoding. What standard FP4 adds on top of that (a mux to bump e=0 to an
  "effective exponent" of 1, because e=0 means something structurally
  different there) is pure overhead this remap doesn't have, since e is
  used unbiased and every exponent value means the same kind of thing.
- **K** only ever takes 3 values, so 2 gates (K's own bits) fully
  determine the outcome - that's the minimum for a 3-way selection
  (needs at least ceil(log2(3))=2 bits of decision). A real 2-bit x 2-bit
  significand multiplier, which is what a naive implementation reaches
  for, computes more distinct outcomes than the format ever produces -
  it's strictly wasted hardware for information that was never there.
- **zero** is a single reused membership test (is the code exactly
  (m=1,e=3)?), not a parallel detection path bolted onto the side. Placing
  zero in the one unused code, instead of carving out dedicated space for
  it elsewhere, is what makes that possible.
- **negation without a real adder**: section 2's thermometer trick isn't a
  clever patch applied after the fact, it's a consequence of the value
  representation itself. 3^K * 2^E always has its lowest set bit exactly
  at E, by construction, for every K and every E the format produces. A
  different representation where the magnitude's lowest bit could land
  anywhere unpredictably would not admit this - it would need a real
  ripple-carry incrementer. The representation was picked such that free
  negation falls out of it, not the other way around.

Every one of these is "cost matches the actual degrees of freedom in the
problem", not "cost matches what's easy to implement." That's the case for
this being close to optimal even before any search runs.

### 4b. automated-search evidence on top of that

Three pieces of evidence from the methodology in section 3, weakest to
strongest, all runnable in `opt/`:

1. **search plateau**: thousands of window-SAT attempts and iterated local
   search restarts (random function-preserving expansions followed by
   re-descent, to escape local optima) stopped finding anything smaller
   than 62. Not proof, but the search had a lot of chances to find fewer.
2. **remap race** (`opt/remap_variants.py`): 33 alternative encodings
   (every exponent-bit-order permutation, every zero placement, magnitude-
   code swaps, the spec's own default mapping) were each scored by splicing
   a minimal translation circuit onto the 62-gate netlist's inputs and
   re-optimizing for a fixed few-minute budget per candidate. None beat 62:
   the best any alternative reached was 64, most landed in the high 60s to
   low 70s. Two honest caveats: the alternatives got minutes of search
   where the incumbent got hours, and the splice-onto-the-incumbent
   starting point favors this encoding's structure - so read this as a
   sanity check that no nearby encoding obviously wins, not as evidence
   against every possible remap (only point 3's universal bound speaks to
   all remaps, and only at small N).
3. **SAT lower bounds** (`opt/lb_sat.py`, exact, not heuristic): a SAT
   solver was asked "does a circuit of N gates exist that matches this
   truth table" for increasing N, with the remap fixed as this one, and
   separately with the remap itself left as a free variable (so an UNSAT
   result there rules out every possible remap, not just this one). Both
   are exhaustive proofs over the full 256-case behavior, not sampling.
   - fixed remap: UNSAT through N=14. Proven floor: **>=15 gates**.
   - any remap: UNSAT through N=12. Proven floor: **>=13 gates**, full
     stop, independent of which encoding you pick.

Point 3 is the only one that's an actual proof, and it only rules out
anything below 13-15 gates - it does not prove 62 is optimal, there's a
real gap between 13-15 and 62. What it does prove is that this problem has
a hard floor in the low teens: no amount of cleverness gets this multiply
down to, say, single digits or even the low 20s, which puts a ceiling on
how much the architectural argument in 4a could possibly be missing.
Combined with the remap race and the search plateau, 62 is very likely
within a handful of gates of the true minimum.

I would love to be shown a solution with less gates, I'm genuinely curious!! :) 

## verification

- `python3 fp4.py`: exhaustive 256-case check against harness.py's
  bit-parallel simulator.
- `verilator --binary rtl/fp4.sv rtl/tb.sv --top-module tb -o tb_sim &&
  ./obj_dir/tb_sim`: same 256 cases, independent RTL simulation.

Both currently report all 256 cases passing at 62 gates.

## opt/

`opt/` has the actual runnable optimizer pipeline behind section 3 and 4b:
don't-care resubstitution, window SAT resynthesis, iterated local search,
the SAT lower-bound prover, and the remap race, each individually smoke-
tested against the numbers cited above. See `opt/README.md` for what each
piece does and how to run it. Left out: a third-party copy of Berkeley ABC
(used once in the reference project for a synthesis comparison, not needed
to reproduce this result), a separate C++/mockturtle optimizer, and the
historical run logs and intermediate checkpoints from the original
multi-worker search - none of that is needed to get from 78 to 62 or to
run the lower-bound proofs yourself.
