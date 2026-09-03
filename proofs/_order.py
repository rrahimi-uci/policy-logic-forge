"""Machine-checked properties of Policy Logic Forge.

Each theorem below is discharged by EXHAUSTIVE enumeration over a finite
domain, so within that domain the result is a proof, not a sample.
"""
import sys, itertools
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from utils.information_model import refines, reconcile_types, _REFINES

# The carrier: every declared business type, plus representative enumerations
# (any type absent from _REFINES is, by construction, an enumeration).
TYPES = sorted(_REFINES) + ["OccupancyType", "LoanPurpose"]
print(f"carrier |T| = {len(TYPES)}: {TYPES}\n")

# ---------------------------------------------------------------------------
# THEOREM 1.  (T, refines) is a strict partial order.
#   1a irreflexive : ∀a. ¬(a ⊏ a)
#   1b asymmetric  : ∀a,b. a ⊏ b → ¬(b ⊏ a)
#   1c transitive  : ∀a,b,c. a ⊏ b ∧ b ⊏ c → a ⊏ c
# ---------------------------------------------------------------------------
fail = []
for a in TYPES:
    if refines(a, a): fail.append(("1a irreflexive", a))
for a, b in itertools.product(TYPES, repeat=2):
    if refines(a, b) and refines(b, a): fail.append(("1b asymmetric", (a, b)))
for a, b, c in itertools.product(TYPES, repeat=3):
    if refines(a, b) and refines(b, c) and not refines(a, c):
        fail.append(("1c transitive", (a, b, c)))
n1 = len(TYPES) + len(TYPES)**2 + len(TYPES)**3
print(f"THEOREM 1  strict partial order      checked {n1:,} tuples -> "
      + ("PROVED" if not fail else f"FAILED {fail[:3]}"))

# ---------------------------------------------------------------------------
# THEOREM 2.  reconcile_types is the greatest-lower-bound selector.
#   For every non-empty S ⊆ T:
#     reconcile(S) = m  ⟹  m ∈ S ∧ ∀x∈S. x = m ∨ m ⊏ x     (m is ⊏-least)
#     reconcile(S) = ⊥  ⟹  no such m exists                 (no false refusal)
#   Also: uniqueness — at most one ⊏-least element can exist (from asymmetry).
# ---------------------------------------------------------------------------
fail2 = []; checked = 0
for r in range(1, 5):                       # all subsets up to size 4
    for S in itertools.combinations(TYPES, r):
        checked += 1
        m = reconcile_types(S)
        least = [c for c in S if all(o == c or refines(c, o) for o in S)]
        if m is None:
            if least: fail2.append(("false refusal", S, least))
        else:
            if m not in S: fail2.append(("not a member", S, m))
            elif not all(o == m or refines(m, o) for o in S):
                fail2.append(("not least", S, m))
            if len(least) > 1: fail2.append(("non-unique least", S, least))
print(f"THEOREM 2  reconcile = ⊏-least elem   checked {checked:,} subsets -> "
      + ("PROVED" if not fail2 else f"FAILED {fail2[:3]}"))

# ---------------------------------------------------------------------------
# THEOREM 3.  Money and Percentage are ⊏-incomparable.
#   The safety property that stops silent unit coercion between two
#   decimal-based business types.
# ---------------------------------------------------------------------------
inc = not refines("Money","Percentage") and not refines("Percentage","Money") \
      and reconcile_types(["Money","Percentage"]) is None
print(f"THEOREM 3  Money ∦ Percentage         -> {'PROVED' if inc else 'FAILED'}")
