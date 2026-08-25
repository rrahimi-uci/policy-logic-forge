# Corpus feature census (theory coverage)

- Total rules: 4
- Run: full-smallest-privacy-20260825
- Scope: One local privacy-policy debugging run from retained metadata-only pipeline output; not a corpus estimate and not a compiler-freeze decision.

## Rule type census

| category | rules |
| --- | ---: |
| `access_rights` | 1 |
| `collection` | 1 |
| `security` | 1 |
| `user_choice` | 1 |

## Variable type census (rules using >=1 variable of this type)

| type | rules |
| --- | ---: |
| `boolean` | 4 |
| `date` | 0 |
| `date_time` | 0 |
| `duration` | 0 |
| `enum` | 4 |
| `list` | 0 |
| `number` | 0 |
| `string` | 1 |

## Value type census (predicate/outcome value_type)

| value_type | rules |
| --- | ---: |
| `boolean` | 4 |
| `date` | 0 |
| `date_time` | 0 |
| `duration` | 0 |
| `enum` | 4 |
| `list` | 0 |
| `number` | 0 |
| `range` | 0 |
| `string` | 1 |
| `variable_reference` | 0 |

## Operator census

| operator | rules |
| --- | ---: |
| `!=` | 0 |
| `<` | 0 |
| `<=` | 0 |
| `==` | 4 |
| `>` | 0 |
| `>=` | 0 |
| `in` | 0 |
| `not_in` | 0 |

## Scope, exception, and hit-policy census

### Scope basis

| category | rules |
| --- | ---: |
| `genuinely_unscoped` | 4 |

### Exception basis

| category | rules |
| --- | ---: |
| `explicitly_none_in_source` | 4 |

### Recommended hit policy

| category | rules |
| --- | ---: |
| `UNIQUE` | 4 |

## Field presence

| field | present | missing |
| --- | ---: | ---: |
| `applicability_scope` | 4 | 0 |
| `condition_logic` | 4 | 0 |
| `exception_basis` | 4 | 0 |
| `exceptions` | 4 | 0 |
| `field_evidence` | 4 | 0 |
| `recommended_hit_policy` | 4 | 0 |
| `scope_basis` | 4 | 0 |
| `source_reference` | 4 | 0 |
| `test_vectors` | 4 | 0 |

## Dependencies and decision-table projections

| category | rules |
| --- | ---: |
| `dependency_edges` | 8 |
| `rules_with_dependencies` | 4 |
| `rules_without_dependencies` | 0 |

| category | rules |
| --- | ---: |
| `rules_with_tables` | 0 |
| `rules_without_tables` | 4 |

## Contract and review signals

- Rules with contract issues: 0
- Rules requiring review: 4
- Invalid predicate operators: 0
- Invalid predicate value types: 0
- Invalid outcome value types: 0
