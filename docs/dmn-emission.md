# BE-2 DMN 1.3 emitter

`utils/dmn_builder.py` and `utils/dmn_emit.py` emit and structurally validate
a conservative DMN 1.3 decision-table projection of LExec IR v1.  The emitter
supports proven `UNIQUE`/`ANY` tables, conjunctions of atomic symbol/literal
conditions, literal/symbol assignments, and unscoped rules.  It renders
deterministic FEEL text and validates namespace, table policy, clause counts,
rule IDs, and non-empty entries without requiring a third-party XML package.

Emission refuses invalid IR, unproved/unknown/timeout policy records,
exceptions, contextual jurisdiction/party/date scope, derived inputs,
non-conjunctive conditions, missing rules, and unsupported policies.  These
refusals are intentional: XML/XSD shape validity cannot repair a semantic loss
at the compiler boundary.

`validate_dmn` is a structural guard, not an XSD validator or an independent
DMN engine.  Semantic equivalence and cross-engine behavior remain BE-4
responsibilities; agreement with the reference evaluator alone is not a
compiler-correctness claim.
