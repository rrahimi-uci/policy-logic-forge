# Corpus feature census (theory coverage)

- Total rules: 6
- Run: ir2-nda-pilot-r2
- Scope: Exploratory pilot: 2 local NDA documents, 1 word-balanced rules batch, pre-optimization graph; not a corpus estimate.

## Rule type census

| category | rules |
| --- | ---: |
| `confidentiality_scope` | 1 |
| `disclosure_exception` | 1 |
| `permitted_disclosure` | 1 |
| `permitted_use` | 3 |

## Variable type census (rules using >=1 variable of this type)

| type | rules |
| --- | ---: |
| `boolean` | 5 |
| `date` | 0 |
| `date_time` | 0 |
| `duration` | 0 |
| `enum` | 1 |
| `list` | 0 |
| `number` | 0 |
| `string` | 5 |

## Value type census (predicate/outcome value_type)

| value_type | rules |
| --- | ---: |
| `boolean` | 5 |
| `date` | 0 |
| `date_time` | 0 |
| `duration` | 0 |
| `enum` | 0 |
| `list` | 0 |
| `number` | 0 |
| `range` | 0 |
| `string` | 5 |
| `variable_reference` | 0 |

## Operator census

| operator | rules |
| --- | ---: |
| `!=` | 0 |
| `<` | 0 |
| `<=` | 0 |
| `==` | 0 |
| `>` | 0 |
| `>=` | 0 |
| `in` | 1 |
| `not_in` | 0 |

## Scope, exception, and hit-policy census

### Scope basis

| category | rules |
| --- | ---: |
| `explicitly_universal_in_source` | 6 |

### Exception basis

| category | rules |
| --- | ---: |
| `explicitly_none_in_source` | 6 |

### Recommended hit policy

| category | rules |
| --- | ---: |
| `UNIQUE` | 6 |

## Field presence

| field | present | missing |
| --- | ---: | ---: |
| `applicability_scope` | 6 | 0 |
| `condition_logic` | 6 | 0 |
| `exception_basis` | 6 | 0 |
| `exceptions` | 6 | 0 |
| `field_evidence` | 6 | 0 |
| `recommended_hit_policy` | 6 | 0 |
| `scope_basis` | 6 | 0 |
| `source_reference` | 6 | 0 |
| `test_vectors` | 6 | 0 |

## Dependencies and decision-table projections

| category | rules |
| --- | ---: |
| `dependency_edges` | 8 |
| `rules_with_dependencies` | 6 |
| `rules_without_dependencies` | 0 |

| category | rules |
| --- | ---: |
| `rules_with_tables` | 0 |
| `rules_without_tables` | 6 |

## Contract and review signals

- Rules with contract issues: 6
- Rules requiring review: 6
- Invalid predicate operators: 5
- Invalid predicate value types: 1
- Invalid outcome value types: 0
