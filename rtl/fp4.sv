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
    assign eff_ea = {ea[1], ea[0] | !ea[1]};
    assign eff_eb = {eb[1], eb[0] | !eb[1]};

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
    assign p = (mag ^ {9{s}}) + s;
endmodule
