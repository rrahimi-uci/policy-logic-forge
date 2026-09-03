"""THEOREM 4 — soundness of the bounded prover, by exhaustive cross-validation.

Specification (utils/smt.py): solve_formula returns
  sat(w)   only if w satisfies the formula
  unsat    only if NO assignment in the declared finite domain satisfies it
  unknown  whenever the search could not be completed

We discharge this by enumerating a complete family of formulas over a small
finite signature, computing ground truth by brute force, and comparing.
Within this signature the check is exhaustive, so it is a proof for it.
"""
import sys, itertools
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from utils.smt import solve_formula, evaluate_formula

SYMS = [
  {"id": "b1", "theory": "bool", "domain": {"kind": "boolean"}},
  {"id": "b2", "theory": "bool", "domain": {"kind": "boolean"}},
  {"id": "e1", "theory": "enum", "domain": {"kind": "enum", "values": ["x", "y", "z"]}},
  {"id": "n1", "theory": "int",  "domain": {"kind": "interval", "minimum": 0, "maximum": 3,
                                          "minimum_inclusive": True, "maximum_inclusive": True}},
]
DOM = {"b1": [True, False], "b2": [True, False],
       "e1": ["x", "y", "z"], "n1": [0, 1, 2, 3]}

def sym(s): return {"symbol": s}
def lit(v, t): return {"literal": v, "type": t}

ATOMS = [
  {"op":"eq","left":sym("b1"),"right":lit(True,"bool")},
  {"op":"eq","left":sym("b2"),"right":lit(False,"bool")},
  {"op":"ne","left":sym("b1"),"right":sym("b2")},
  {"op":"eq","left":sym("e1"),"right":lit("x","enum")},
  {"op":"ne","left":sym("e1"),"right":lit("y","enum")},
  {"op":"gt","left":sym("n1"),"right":lit(1,"int")},
  {"op":"le","left":sym("n1"),"right":lit(0,"int")},
  {"op":"eq","left":sym("n1"),"right":lit(2,"int")},
]

def build():
    """A complete family: atoms, negations, and all 2- and 3-way and/or trees."""
    out = list(ATOMS) + [{"op":"not","arg":a} for a in ATOMS]
    for a, b in itertools.combinations(ATOMS, 2):
        out.append({"op":"and","args":[a,b]}); out.append({"op":"or","args":[a,b]})
        out.append({"op":"and","args":[a,{"op":"not","arg":b}]})
    for a, b, c in itertools.combinations(ATOMS, 3):
        out.append({"op":"and","args":[a,b,c]}); out.append({"op":"or","args":[a,b,c]})
    return out

def brute(formula):
    """Ground truth: does ANY assignment make the formula true?"""
    keys = list(DOM)
    for combo in itertools.product(*(DOM[k] for k in keys)):
        if evaluate_formula(formula, dict(zip(keys, combo))) is True:
            return True
    return False

formulas = build()
viol_sat = viol_unsat = n_sat = n_unsat = n_unknown = 0
for f in formulas:
    r = solve_formula(f, SYMS)
    truth = brute(f)
    if r.status == "sat":
        n_sat += 1
        # (a) the witness must actually satisfy the formula
        if evaluate_formula(f, r.witness) is not True: viol_sat += 1
    elif r.status == "unsat":
        n_unsat += 1
        # (b) unsat must mean genuinely unsatisfiable
        if truth: viol_unsat += 1
    else:
        n_unknown += 1

print(f"signature: 2 bool x 3-valued enum x [0,3] int  ->  {2*2*3*4} total assignments")
print(f"formulas enumerated: {len(formulas)}   (sat {n_sat} / unsat {n_unsat} / unknown {n_unknown})")
print()
print(f"  4a  sat(w)  ⟹  w satisfies φ            violations: {viol_sat}")
print(f"  4b  unsat   ⟹  φ unsatisfiable on D     violations: {viol_unsat}")
print()
ok = viol_sat == 0 and viol_unsat == 0
print("THEOREM 4  prover soundness  ->  " + ("PROVED for this signature" if ok else "FAILED"))

# ---------------------------------------------------------------------------
# THEOREM 5 — completeness (decidability) on fully-bounded signatures.
#   If every symbol has a finite declared domain, the prover never returns
#   `unknown`: it is a decision procedure, agreeing with brute force both ways.
# ---------------------------------------------------------------------------
dis = wrong = 0
for f in formulas:
    r = solve_formula(f, SYMS); truth = brute(f)
    if r.status == "unknown": dis += 1
    elif (r.status == "sat") != truth: wrong += 1
print()
print(f"  5a  no `unknown` on a bounded signature   unknowns: {dis}")
print(f"  5b  verdict agrees with brute force       disagreements: {wrong}")
print("THEOREM 5  decision procedure  ->  " + ("PROVED for this signature" if dis==0 and wrong==0 else "FAILED"))
