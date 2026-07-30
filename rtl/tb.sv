// Exhaustive self-checking testbench: all 256 input pairs against a golden
// model (value tables in halves; expected pattern = (2*va) * (2*vb) mod 512).
module tb;
    logic [3:0] a, b;
    logic [8:0] p;

    fp4_mul dut (.a(a), .b(b), .p(p));

    // remapped code {s,e1,e0,m} -> 2*value; (m=1,e=3) is zero, both signs
    function automatic int v2(input logic [3:0] c);
        case (c)
            4'b0000: return 1;   4'b0001: return 3;   4'b0010: return 2;
            4'b0011: return 6;   4'b0100: return 4;   4'b0101: return 12;
            4'b0110: return 8;   4'b0111: return 0;   4'b1000: return -1;
            4'b1001: return -3;  4'b1010: return -2;  4'b1011: return -6;
            4'b1100: return -4;  4'b1101: return -12; 4'b1110: return -8;
            default: return 0;
        endcase
    endfunction

    int errors = 0;
    initial begin
        for (int i = 0; i < 16; i++) begin
            for (int j = 0; j < 16; j++) begin
                a = i[3:0];
                b = j[3:0];
                #1;
                if (p !== 9'((v2(a) * v2(b)) & 511)) begin
                    errors++;
                    $display("MISMATCH a=%b b=%b: got %b want %b",
                             a, b, p, 9'((v2(a) * v2(b)) & 511));
                end
            end
        end
        if (errors == 0) $display("all 256 cases pass");
        else             $display("%0d failures", errors);
        $finish;
    end
endmodule
