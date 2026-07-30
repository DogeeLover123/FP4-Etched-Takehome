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

    // zero iff (m=1, e=3) -- that (m,e) combo is unused by real fp4 values,
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
    assign K = ma + mb; // NOTE: adding 2 1 bit numbers is just a half adder

    // sign
    logic s;
    assign s = sa ^ sb;

    // thermometer code t_j = [E <= j] (E in [0,6], so t6=t7=1 always -- no
    // gates needed for those, they're used as literal 1 below). indexes
    // straight into E instead of re-deriving its bits.
    logic nE2, u, v;
    assign nE2 = ~E[2];
    assign u   = E[1] | E[0];
    assign v   = E[1] & E[0];

    logic t0, t1, t2, t3, t4, t5;
    assign t0 = ~(E[2] | u);
    assign t1 = ~(E[2] | E[1]);
    assign t2 = nE2 & ~v;
    assign t3 = nE2;
    assign t4 = ~(E[2] & u);
    assign t5 = ~(E[2] & E[1]);

    // onehot decode d_j = t_j ^ t_{j-1} -- this IS the shifter, no mux tree
    logic d0, d1, d2, d3, d4, d5, d6;
    assign d0 = t0;
    assign d1 = t1 ^ t0;
    assign d2 = t2 ^ t1;
    assign d3 = t3 ^ t2;
    assign d4 = t4 ^ t3;
    assign d5 = t5 ^ t4;
    assign d6 = 1'b1 ^ t5;   // t6 = 1
    // d7 = t7 ^ t6 = 1 ^ 1 = 0 -- E never reaches 7

    // unsigned product bits: bit0 of 3^K always set -> d_j; bit1 set iff
    // K==1 -> K[0] & d_{j-1}; bit3 set iff K==2 -> K[1] & d_{j-3}
    logic P0, P1, P2, P3, P4, P5, P6, P7;
    assign P0 = d0;
    assign P1 = d1 | (K[0] & d0);
    assign P2 = d2 | (K[0] & d1);
    assign P3 = d3 | (K[0] & d2) | (K[1] & d0);
    assign P4 = d4 | (K[0] & d3) | (K[1] & d1);
    assign P5 = d5 | (K[0] & d4) | (K[1] & d2);
    assign P6 = d6 | (K[0] & d5) | (K[1] & d3);
    assign P7 = K[1] & d4;
    // P8 = 0 -- max real product never reaches bit 8

    // signed output: two's complement of P (lowest set bit always at E) is
    // bits below E stay 0, bit E stays 1, bits above E flip -- ~P is all 1s
    // below E, the "+1" ripples those back to 0 and carries into bit E,
    // then stops. so out_j = P_j ^ (s & t_{j-1}) does the whole negation
    // with the same t-chain already built for the shift. then mask to 0 if
    // either operand was zero.
    assign p[0] = P0 & ~is_zero;                  // t_{-1} = 0
    assign p[1] = (P1 ^ (s & t0)) & ~is_zero;
    assign p[2] = (P2 ^ (s & t1)) & ~is_zero;
    assign p[3] = (P3 ^ (s & t2)) & ~is_zero;
    assign p[4] = (P4 ^ (s & t3)) & ~is_zero;
    assign p[5] = (P5 ^ (s & t4)) & ~is_zero;
    assign p[6] = (P6 ^ (s & t5)) & ~is_zero;
    assign p[7] = (P7 ^ s) & ~is_zero;             // t6 = 1
    assign p[8] = s & ~is_zero;                    // P8 = 0, t7 = 1 -> core = s
endmodule
