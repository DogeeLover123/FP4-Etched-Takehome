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

    // zero iff (m=1, e=3)
    // this (m,e) combo is unused by real fp4 values,
    // so both signs of it double as the zero codes
    logic za, zb, is_zero;
    assign za = ma & ea[1] & ea[0];
    assign zb = mb & eb[1] & eb[0];
    assign is_zero = za | zb;

    // exponent sum - no subrnomal correction needed now! 
    // there is also 0 bias to account for
    logic [2:0] E;
    assign E = ea + eb;

    // K = ma + mb in {0,1,2} picks the significand product 3^K in {1,3,9}
    // K = 4'b0001, 4'b0011, 4'b1001 which is a fixed pattern with only bit 3 and bit 1 changing
    logic [1:0] K;
    logic [3:0] mp;
    assign K  = ma + mb; // NOTE: adding 2 1 bit numbers is just a half adder
    assign mp = {K[1], 1'b0, K[0], 1'b1};

    // shift to convert into unsigned integer value
    logic [8:0] mag;
    assign mag = 9'(mp) << E;

    // 2s complement if product is negative, then mask to 0 if either
    // operand was zero
    logic s;
    assign s = sa ^ sb;
    assign p = ((mag ^ {9{s}}) + s) & {9{~is_zero}};
endmodule
