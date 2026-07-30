This commit switches the input encoding from standard FP4 to a custom remap.
Same architecture as last commit (barrel shifter + XOR-negate trick) - the
win here is entirely from a smarter code assignment, not a new circuit trick.

so the key idea is since that we know we have to multiply by 4 anyways, its
good to double each of the operands. 2*2=4 so then that already accounts for
the 4x. its also good because we get rid of decimal.

Now the input operands are 0,1,2,3,4,6,8,12, (also + or -) and we see this is
{1,3}*2^{0,1,2,3}. except the case for 3*2^3=24 doesn't exist (we only have
up to 12) so this is perfect as we can use this to represent 0.

for the exponent {0,1,2,3}, we can use the existing 2 bit exponent so that
part is the same. the sign bit is also the same, so the only thing that is
different is that now the mantissa bit just represents either 1, or 3.

code bits stay in the same order as standard FP4, (s, e1, e0, m) - only what
they mean changes: value = (-1)^s * (1+2m) * 2^(e-1), zero lives at (m=1,
e=3) for both signs (that's the "24" combo that doesn't exist).

what this buys you over standard FP4:

- no more subnormal handling. old design needed a mux to bump e=0 up to
  "effective exponent or eff" 1. this new design just feeds e straight into the adder, 
  so no such case exists anymore.
- no more real 2x2 significand multiplier. old mp was a genuine 2bit x 2bit
  multiply (4 partial-product ANDs + carry combine). new mp only has to 
  represent 3 values: {1,3,9}. This can be represented by 3^K!! 
  K = ma+mb in {0,1,2}. 
  Since K only is 4'b0001, 4'b0011, 4'b1001, notice only bit 1 and bit 3 change - selected by 2 gates (K's bits), no multiplier array at all!!
- exponent add loses its "-2" correction. old design computed
  eff_ea+eff_eb-2 (folded into the adder outputs). new E = ea+eb directly -
  the remap's built-in 2^(e-1) already accounts for what the "-2" used to
  do, so the raw adder output feeds the shifter unmodified.
- zero handling changes shape. old design got zero for free out of the
  significand (m=0,e=0 naturally multiplies to 0). new design needs an
  explicit check instead: an operand is zero iff (m=1 and e=3), a 3-input
  AND. OR that across both operands, then AND it across all 9 output bits
  at the very end.

barrel shifter and final negate are otherwise structurally identical to the
previous commit (same "shifted-in bits are known 0" collapse, same
XOR+ripple negate-and-add-sign trick). Shift range grew from 0-4 to 0-6
since there's no more "-2" to shrink it, but that's still a 3-bit shift
amount either way, so no extra shifter stage was needed.

gate breakdown (fp4.py):

- zero check (za, zb, is_zero, ~is_zero): 6
- sign (sa^sb): 1
- exponent adder (E = ea+eb, 2bit+2bit): 7
- K (ma+mb, picks the 3^K pattern): 2
- barrel shift stage 1 (shift by E0, 0/1): 6
- barrel shift stage 2 (shift by E1, 0/2): 14
- barrel shift stage 3 (shift by E2, 0/4): 18
- negate (XOR by sign + ripple add sign): 26
- final zero mask (AND every output bit with ~is_zero): 9

total: 89 gates, verified all 256 cases pass (fp4.py + rtl/tb.sv via
verilator)

only 1 gate less than last commit (90) even though the remap saves ~14 gates
(no real multiplier, no -2 fold, more constant-folding in the shifter)
almost all of it gets eaten by the new 9-gate zero mask ({9{~is_zero}}), which standard FP4
got for free and this encoding doesn't. next commit will have
to find a solution for this...
