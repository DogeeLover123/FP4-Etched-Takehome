/*
First implementation is going to just go with a similar approach that I've used for previous
floating point designs

where we convert the floating point numbers into some fixed point format to make the multiplication easy

but instead of normalizing back to floating point keep it in fixed format.

for fp4, we have just one mantissa bit, so we either have x.0 or x.1 (either no decimal or .5)

BUT since we know we're going to be multiplying by 4 anyways, we can just multiply each input operand by 2
and now when we multiply these inputs this already handles the multiply by 4 as 2x2=4

this gets rid of the decimal value too because .5*2=1
so now for the 'mantissa' previously we had
0.1, 1.0, or 1.1
So now its 01.0, 10.0, 11.0

this is the same thing, but just the significance is doubled

product of these two is a 4 bit integer value

and now we just shift left by (ea - bias) + (eb - bias), where the bias for fp4 is 1

we have to fill the upper remaining bits with 0s

this gives us an unsigned integer value, and to get a signed integer value we just 2s complement
which is just negation + 1!!


I'm writing verilog solution to get something done quick, and then I can reason as to how it would map onto logic gates

I know a 1 bit full adder is 5 logic gates
         a 1 bit mux is 4 logic gates
         a 2 bit multiplier is 8 logic gates

assign siga = {ea[1]|ea[0], ma}; - 1 logic gate
assign sigb = {eb[1]|eb[0], mb}; - 1 logic gate

 assign eff_ea = (ea == 2'd0) ? 2'd1 : ea;
 ea == 2'd0 - to check if a bit is 0, you can NOT it and then AND it with a 1 - therefore 2 bits per bit
 given there are 2 bits, there are 4 logic gates involved

 This is followed by a 2 bit mux, which is 8 logic gates

 Therefore this one line is 12 logic gates

 assign eff_eb = (eb == 2'd0) ? 2'd1 : eb; - also 12 logic gates

 assign mp = siga * sigb; - 8 logic gates

 assign sh = eff_ea + eff_eb - 3'd2; - adding eff_ea+eff_eb needs a 2 bit adder (10 gates), then
 subtracting 3'd2 is another add, this time a 3 bit adder (15 gates) - therefore this line is 25 gates

 assign mag = 9'(mp) << sh; - shift amount here is a signal not a constant, so this is a real
 barrel shifter, not free - 3 mux stages (shift by 1, then 2, then 4) - about 21 muxes total,
 4 gates each - 84 gates

 assign s = sa ^ sb; - 1 gate

 assign p = s ? (~mag + 9'd1) : mag;

 ~mag is inverting every bit, for all 9 bits - 9 gates

 followed by a 9 bit adder - 45 gates

 followed by a 9 bit mux - 36 gates

 therefore this one line takes 9 + 45 + 36 = 90 gates

total: 1+1+12+12+8+25+84+1+90 = 234 gates

things to optimize next: barrel shifter is the biggest cost by far (84 gates) so that's the first
target, and a lot of the rest is just not exploiting constants - eg the eff_ea/eff_eb mux against
a constant, the +1 against a constant, should all collapse way down
*/

module fp4_mul (
    input  logic [3:0] a,   // {s, e1, e0, m}
    input  logic [3:0] b,
    output logic [8:0] p
);
    // ---- field extraction ----
    logic       sa, sb, ma, mb;
    logic [1:0] ea, eb;

    assign sa = a[3];
    assign ea = a[2:1];
    assign ma = a[0];

    assign sb = b[3];
    assign eb = b[2:1];
    assign mb = b[0];


    // significand: 2 bit x.x value that we multiply together
    logic [1:0] siga, sigb;

    // upper bit is 1 if not subnormal: we know its not subnormal if any of the bits are 1 so bitwise OR
    assign siga = {ea[1]|ea[0], ma};
    assign sigb = {eb[1]|eb[0], mb};
    // effective exponent: subnormals have e=1
    logic [1:0] eff_ea, eff_eb;
    assign eff_ea = (ea == 2'd0) ? 2'd1 : ea;
    assign eff_eb = (eb == 2'd0) ? 2'd1 : eb;

    // 2x2 bit significand multiply is a 4 bit output
    logic [3:0] mp;
    assign mp = siga * sigb;

    // max value of eff_ea + eff_eb - 2 is 3+3-2=4 which needs 3 bits to represent
    logic [2:0] sh;
    assign sh = eff_ea + eff_eb - 3'd2;

    // shift to convert into unsigned integer value -- NOT free, see comment block above
    logic [8:0] mag;
    assign mag = 9'(mp) << sh;

    // 2s complement if product is negative
    logic s;
    assign s = sa ^ sb;
    assign p = s ? (~mag + 9'd1) : mag;
endmodule
