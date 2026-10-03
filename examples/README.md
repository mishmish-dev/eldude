# Eldude implementation targets

These small `.eld` programs are staged targets for a future compiler. They are syntax-checked today; there is no Eldude type checker or runtime in this repository yet. Each positive file is a separate program. A future test harness should call its exported `main` and compare its returned value below; `main` is a corpus convention, not a new language entry-point rule. Task examples need a root supporting `suspend`.

Resolve explicit library imports using the module declarations in [stdlib](../stdlib/README.md). Primitive types and intrinsic constraints have their predefined meanings. There is no implied wildcard library prelude. The bundled profile binds list literals, `?`/`try`, optional access, `for`, cleanup, and task handles to their corresponding library identities.

| Stage | Program | Expected value | Capability |
| --- | --- | --- | --- |
| 1 | [literal](01_values/literal.eld) | `42` | Function and integer literal |
| 1 | [arithmetic](01_values/arithmetic.eld) | `14` | Precedence |
| 1 | [branches](01_values/branches.eld) | `7` | Conditional and unary arithmetic |
| 1 | [tuples](01_values/tuples.eld) | `42` | Tuple construction/destructuring |
| 1 | [records](01_values/records.eld) | `9` | Nominal records and field copies |
| 1 | [enums](01_values/enums.eld) | `42` | Exhaustive matching |
| 1 | [closures](01_values/closures.eld) | `42` | Captures and repeated invocation |
| 1 | [generics](01_values/generics.eld) | `42` | Type parameters and turbofish |
| 1 | [startup](01_values/startup.eld) | `42` | Ordered pure top-level initialization |
| 2 | [structural recursion](02_ownership/structural_recursion.eld) | `42` | Finite inductive recursion |
| 2 | [numeric recursion](02_ownership/numeric_recursion.eld) | `6nat` | Unproved termination requires `diverge`, including at the caller |
| 2 | [view](02_ownership/view.eld) | `42` | Scoped inspection followed by consumption |
| 2 | [linear closure](02_ownership/linear_closure.eld) | `42` | Transfer into a closure |
| 2 | [traits](02_ownership/traits.eld) | `42` | Covered impl and associated type |
| 3 | [option](03_results/option.eld) | `42` | Library method and lazy fallback |
| 3 | [propagation](03_results/propagation.eld) | `42` | Error identity and `?` |
| 3 | [try scope](03_results/try_scope.eld) | `42` | Local error propagation |
| 4 | [handler](04_effects/handler.eld) | `42` | Tail clause returns its operation result for automatic resumption |
| 4 | [generic instances](04_effects/generic_instances.eld) | `42` | Distinct `Read<Int>`/`Read<Bool>` instances |
| 4 | [once](04_effects/once.eld) | `42` | Work after resumption; parent-local handler |
| 4 | [nested layers](04_effects/nested_layers.eld) | `42` | Named outer dispatch survives handling an inner instance |
| 4 | [forwarding](04_effects/forwarding.eld) | `42` | Forwarded operation keeps its outer effect requirement |
| 4 | [tail result](04_effects/tail_result.eld) | `42` | Clause-local `?` supplies an error result to the caller |
| 5 | [local state](05_state_and_collections/local_state.eld) | `42` | Regional cell and state elimination |
| 5 | [list failure](05_state_and_collections/list_failure.eld) | `3nat` | Failed removal returns original collection |
| 5 | [finite loop](05_state_and_collections/finite_loop.eld) | `42` | Ownership-threaded finite iteration |
| 5 | [freeze](05_state_and_collections/freeze.eld) | `2nat` | Capture-free elements escape after freezing through a generic wrapper |
| 5 | [cleanup](05_state_and_collections/cleanup.eld) | `1` | `using` discharges a linear guard |
| 5 | [tail cleanup](05_state_and_collections/tail_cleanup.eld) | `42` | Clause-local early return cleans up before resumption |
| 6 | [join](06_tasks/join.eld) | `42` | Spawn and await |
| 6 | [inherited handler](06_tasks/inherited_handler.eld) | `42` | Same inherited handler, different child result types |
| 6 | [child-local handler](06_tasks/child_local_handler.eld) | `42` | Answer-changing handler inside a child |
| 6 | [library join](06_tasks/library_join.eld) | `42` | Higher-order task composition |

## Rejection targets

`reject/syntax` must fail the grammar recognizer now. `reject/semantics` must parse, but a future type checker must reject it for the stated reason. Passing the current syntax suite does not establish any of these semantic rejections.

| Program | Required failure |
| --- | --- |
| [missing loop separator](reject/syntax/missing_loop_separator.eld) | Missing `;` after a nonfinal loop |
| [effect application](reject/syntax/effect_application.eld) | Expression type application needs `::<...>` |
| [multiple row tails](reject/syntax/multiple_row_tails.eld) | Only one tail may follow `|` |
| [decreases annotation](reject/syntax/decreases_annotation.eld) | Symbolic termination annotations are deferred |
| [linear discard](reject/semantics/linear_discard.eld) | Unconsumed linear binding |
| [uncovered impl](reject/semantics/uncovered_impl.eld) | Impl parameter absent from its head |
| [inherited answer change](reject/semantics/inherited_answer_change.eld) | Baseline handler cannot preserve arbitrary child results |
| [region escape](reject/semantics/region_escape.eld) | Returned closure retains a local cell |
| [whole argument capture](reject/semantics/whole_argument_capture.eld) | Returning one opaque tuple member conservatively retains the whole argument |
| [await whole argument capture](reject/semantics/await_whole_argument_capture.eld) | Awaiting a task returned through a helper preserves the helper's conservative capture bound |
| [freeze captured elements](reject/semantics/freeze_captured_elements.eld) | Capture-bearing elements preserve the frozen owner's region dependency |
| [mutable capture escape](reject/semantics/mut_capture_escape.eld) | A wrapper returning `Unit` leaves an inner capture in an outer mutable owner |
| [explicit tail resume](reject/semantics/tail_explicit_resume.eld) | A `tail` clause must return the operation result |
| [row variable entry](reject/semantics/row_variable_entry.eld) | A row variable cannot occupy a fixed effect-entry position |
| [numeric recursion without diverge](reject/semantics/numeric_recursion_without_diverge.eld) | Numeric descent does not establish structural recursion |
| [while without diverge](reject/semantics/while_without_diverge.eld) | Every `while` requires `diverge` in the initial core |

Run the checks from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tools/check_grammar.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools -p 'test_*.py'
```
