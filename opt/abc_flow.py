"""Remap-table builder for the (s, m, e) scheme.

Trimmed from the reference project's abc_flow.py: dropped everything to do
with driving external ABC synthesis (not needed here, and not something
this repo depends on). Just the remap table generator, since baseline.py,
ils.py, and remap_variants.py all need it as their reference starting
remap.
"""


def remap_sme(s_pos=0):
    """code bits (b3,b2,b1,b0) = (s, m, e1, e0); v2 = (-1)^s * (1+2m) * 2^e; zero at (m=1,e=3)."""
    remap = []
    for code in range(16):
        s, m, e = (code >> 3) & 1, (code >> 2) & 1, code & 3
        if m == 1 and e == 3:
            v = 0
        else:
            v = (3 if m else 1) << e
            if s:
                v = -v
        remap.append(v)
    return tuple(remap)
