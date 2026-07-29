This commit has the exact same design and verilog code. It just optimizes 
the boolean logic. 

For instructions on design architecture, see previous commit (first commit)

To summarize, I used following optimizations:

- eff_ea/eff_eb: mux against a constant is dumb, just OR the bits directly, no mux needed
- sh - 2: constant subtract, fold it straight into the adder outputs instead of a second adder
- barrel shifter: shifted-in bits are known 0s, most muxes collapse down to a single AND
- final negate line: Don't need mux logic with sign bit as select line, can just do bitwise XOR with sign bit. And then since we're adding by constant we can just use a half adder which is only 2 logic gates (AND and OR) 

line by line breakdown below (numbers for the verilog code as written, none of it changed - just
how you map each line to gates changed)

assign siga = {ea[1]|ea[0], ma};
assign sigb = {eb[1]|eb[0], mb}; - 2 gates total (1 OR each, ma/mb are direct wires)

old: assign eff_ea = (ea == 2'd0) ? 2'd1 : ea;
new: assign eff_ea = {ea[1], ea[0] | !ea[1]}; 
- if e1 is 1 the value is
already >=2 so e0 doesn't matter, and if e1 is 0 you're going to have 1 anyways, regardless of what ea[0] is. So just one NOT and OR gate - 4 gates total for both
eff_ea and eff_eb

assign mp = siga * sigb; - 4 partial product ANDs + 2 XOR/AND pairs to combine them - 8 gates

assign sh = eff_ea + eff_eb - 3'd2; - 2 bit adder for eff_ea+eff_eb 
- (2 gates for first bit half adder, then 5 gates for 2nd bit full adder: 2+5= 7 gates) t
Then have to add -2 - apparently since its a constant it can be done in just 2 more logic gates. To be honest don't fully understand how this process works but synthesis tools should manage this themslevss normally. 

assign mag = 9'(mp) << sh; - barrel shifter, 3 mux stages, but a lot of the shifted-in bits are
known 0s so most of those muxes collapse down to a single AND - 41 gates

assign s = sa ^ sb; - 1 gate

old: assign p = s ? (~mag + 9'd1) : mag;
new: assign p = (mag ^ {9{s}}) + s; - instead of computing ~mag+1 and mag separately and muxing
between them, XOR every bit with s first (that's the invert-if-negative part) then add s (not a
constant 1 - has to be s, since we only want +1 when negating) - one pass does the invert, the
+1, and the select together - 25 gates

total: 2+4+8+9+41+1+25 = 90 gates, verified all 256 cases pass (fp4.py)
