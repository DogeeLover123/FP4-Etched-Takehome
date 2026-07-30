module fp4_mul (
    input  logic [3:0] a,   // {s, e1, e0, m}
    input  logic [3:0] b,
    output logic [8:0] p
);
    // 62-gate netlist found by automated search (don't-care resubstitution +
    // window SAT resynthesis) starting from last commit's 78-gate hand
    // design -- see fp4.py / README.md for the methodology. This is search
    // output, not hand-written, so it's a flat, opaque chain rather than
    // named/grouped logic like previous commits.
    logic n1, n2, n3, n4, n5, n6, n7, n8, n9, n10;
    logic n11, n12, n13, n14, n15, n16, n17, n18, n19, n20;
    logic n21, n22, n23, n24, n25, n26, n27, n28, n29, n30;
    logic n31, n32, n33, n34, n35, n36, n37, n38, n39, n40;
    logic n41, n42, n43, n44, n45, n46, n47, n48, n49, n50;
    logic n51, n52, n53, n54, n55, n56, n57, n58, n59, n60;
    logic n61, n62;

    assign n1 = a[1] & a[2];
    assign n2 = b[1] & b[2];
    assign n3 = a[1] ^ b[1];
    assign n4 = a[1] & b[1];
    assign n5 = a[2] ^ b[2];
    assign n6 = n4 ^ n5;
    assign n7 = a[2] & b[2];
    assign n8 = n4 & n5;
    assign n9 = a[0] ^ b[0];
    assign n10 = n3 & n6;
    assign n11 = n7 | n8;
    assign n12 = ~n11;
    assign n13 = n10 ^ n12;
    assign n14 = n6 & n13;
    assign n15 = n3 & n13;
    assign n16 = n14 ^ n13;
    assign n17 = n15 ^ n16;
    assign n18 = a[0] & b[0];
    assign n19 = n17 & n18;
    assign n20 = n14 & n18;
    assign n21 = n3 & n11;
    assign n22 = n9 & n21;
    assign n23 = a[3] ^ b[3];
    assign n24 = n17 & n23;
    assign n25 = a[0] & n1;
    assign n26 = b[0] & n2;
    assign n27 = n25 | n26;
    assign n28 = ~n27;
    assign n29 = n23 & n28;
    assign n30 = n18 & n11;
    assign n31 = n9 & n15;
    assign n32 = n10 & n18;
    assign n33 = n3 | n9;
    assign n34 = n6 & n33;
    assign n35 = n33 & n11;
    assign n36 = n16 & n33;
    assign n37 = n23 & n13;
    assign n38 = n14 | n37;
    assign n39 = n9 & n10;
    assign n40 = n15 & n18;
    assign n41 = n6 & n11;
    assign n42 = n23 | n11;
    assign n43 = n41 ^ n42;
    assign n44 = n21 ^ n43;
    assign n45 = n23 & n44;
    assign n46 = n32 ^ n23;
    assign n47 = n19 | n34;
    assign n48 = n39 | n40;
    assign n49 = n20 | n35;
    assign n50 = n22 ^ n46;
    assign n51 = n37 ^ n47;
    assign n52 = n44 ^ n48;
    assign n53 = n45 ^ n49;
    assign n54 = n41 | n50;
    assign n55 = n30 ^ n23;
    assign n56 = n24 ^ n36;
    assign n57 = n28 & n51;
    assign n58 = n28 & n52;
    assign n59 = n28 & n53;
    assign n60 = n28 & n54;
    assign n61 = n28 & n55;
    assign n62 = n31 ^ n38;

    // output bit j -> gate producing it (see fp4.py build_fp4() outputs)
    assign p[0] = n17;
    assign p[1] = n56;
    assign p[2] = n62;
    assign p[3] = n57;
    assign p[4] = n58;
    assign p[5] = n59;
    assign p[6] = n60;
    assign p[7] = n61;
    assign p[8] = n29;
endmodule
