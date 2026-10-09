# Eldude examples

<a id="eldude-implementation-targets"></a>

[Documentation and project map](../docs/index.md) · [Implementation support and limits](../tools/README.md#source-to-execution-experiment)

[Positive programs](#positive-programs) · [Source fixtures](#executable-source-fixtures) · [Test host](#fixture-host-profile) · [Rejections](#rejection-targets) · [Handler counterexamples](#enforced-source-rejections)

All **82 positive examples** execute through the source checker and interpreter. Each file is a separate program; the runner uses the documented [entry-point convention](../tools/README.md#entry-point-api-and-diagnostics).

```sh
uv run python tools/run_eldude.py --examples --strict
# 82 passed, 0 unsupported, 0 failed
```

[manifest.json](manifest.json) records independently specified expected values for every positive file. Corpus execution fails for wrong values, unexpected diagnostics, missing manifest entries, or regressions. `--strict` also rejects pending implementation limits; there are currently none in this corpus. Rejection fixtures are checked separately by the test suite.

| Stage | Runnable | Capabilities exercised |
| --- | ---: | --- |
| [1. Values](01_values) | 9 / 9 | Arithmetic, closures, generics, records, tuples, enums and startup |
| [2. Ownership](02_ownership) | 24 / 24 | Linear nominal types, capture contracts, inspection, recursion and trait erasure |
| [3. Results](03_results) | 3 / 3 | Library imports, matching, `?` and `try` |
| [4. Effects](04_effects) | 6 / 6 | Generic instances, handlers, forwarding and `Result` payloads |
| [5. State and collections](05_state_and_collections) | 17 / 17 | Regions, captured callbacks, collection primitives, iteration and cleanup traits |
| [6. Tasks](06_tasks) | 5 / 5 | Cooperative scheduling, task groups, spawn/await and library join |
| [7. Source pipeline](07_source_pipeline) | 17 / 17 | Handler evidence, ownership, resumption and cleanup regressions |
| [8. Formatting](08_formatting) | 1 / 1 | Source formatting preserves field evaluation order, handlers and precedence |

Resolve explicit library imports using the module declarations in [stdlib](../stdlib/README.md). Primitive types and intrinsic constraints have their predefined meanings. There is no implied wildcard library prelude. The bundled profile binds list literals, `?`/`try`, optional access, `for`, cleanup, and task handles to their corresponding library identities.

## Positive programs

Stages 1–6 introduce the language features below. Stage 7 contains the focused [source pipeline fixtures](#executable-source-fixtures).

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
| 2 | [explicit captures](02_ownership/explicit_captures.eld) | `42` | A named capture contract preserves linear ownership |
| 2 | [parameter captures](02_ownership/parameter_capture.eld) | `42` | A factory transfers its file into a returned callable; one explicit close |
| 2 | [capture rows](02_ownership/capture_rows.eld) | `42` | Generic callback forwarding preserves linear usage; bounded repetition |
| 2 | [existentials](02_ownership/existentials.eld) | `42` | Distinct concrete values share a checked dynamic trait interface |
| 2 | [existential arguments](02_ownership/existential_arguments.eld) | `42` | Full instantiated interfaces across all six generic categories |
| 2 | [existential associated types](02_ownership/existential_associated.eld) | `42` | Fixed associated results dispatch without exposing the hidden type |
| 2 | [existential constraints](02_ownership/existential_constraints.eld) | `42` | Trait, method and implementation prerequisites with visible usage evidence |
| 2 | [existential traits](02_ownership/existential_traits.eld) | `42` | One hidden value supplies several dictionaries; bound weakening preserves storage |
| 2 | [associated only](02_ownership/associated_only.eld) | `42` | Associated-only implementation registers its equation |
| 2 | [associated decrease](02_ownership/associated_decrease.eld) | `42` | Smaller projection inputs normalize with their prerequisites |
| 2 | [associated alias](02_ownership/associated_alias.eld) | `42` | Acyclic local associated aliases expand |
| 2 | [generic alias](02_ownership/generic_alias.eld) | `42` | Generic aliases instantiate before implementation selection |
| 2 | [generic projection](02_ownership/generic_projection.eld) | `42` | Projection identity retains the explicit trait arguments |
| 2 | [existential effect row](02_ownership/existential_effect_row.eld) | `42` | Implementation rows match closed interfaces and flow through generic erased calls and associated callbacks |
| 2 | [capture trait bounds](02_ownership/capture_trait_bounds.eld) | `42` | Inherited capture-row evidence flows through erased helpers and associated duplicable callbacks |
| 2 | [existential callback factory](02_ownership/existential_callback_factory.eld) | `42` | Dynamic method result names its own callback parameter |
| 2 | [generic kinds](02_ownership/generic_kinds.eld) | `42` | Explicit constructor and natural arguments preserve declared kinds |
| 2 | [nonabandoning](02_ownership/nonabandoning.eld) | `42` | Tail-only effect evidence permits a linear file to remain live across a generic call |
| 2 | [traits](02_ownership/traits.eld) | `42` | Covered impl and associated type |
| 2 | [trait prerequisites](02_ownership/trait_prerequisites.eld) | `42` | Decreasing element constraints and normalized associated results |
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
| 5 | [captured callback](05_state_and_collections/captured_callback.eld) | `42` | Explicit region/value captures survive higher-order forwarding |
| 5 | [parameter captures](05_state_and_collections/parameter_capture.eld) | `42` | Nested factories and shadowed cells preserve distinct argument sources |
| 5 | [affine capture row](05_state_and_collections/affine_capture_row.eld) | `42` | Generic relay retains a nonduplicable array callback |
| 5 | [inferred regions](05_state_and_collections/inferred_regions.eld) | `42` | Joint callback/type/effect constraints in either argument order |
| 5 | [explicit regions](05_state_and_collections/explicit_regions.eld) | `42` | Ordered explicit region and capture-row arguments |
| 5 | [forwarded mutation](05_state_and_collections/forwarded_mut.eld) | `1nat` | Two helpers forward one grant to the same array |
| 5 | [projected mutation](05_state_and_collections/projected_mut.eld) | `42` | Parent projection, independent inner state, and skipped callback on lookup miss |
| 5 | [mutation exits](05_state_and_collections/mut_exit_paths.eld) | `42` | Early return, recoverable failure and affine abandonment release the interval |
| 5 | [mutation suspension](05_state_and_collections/mut_suspension.eld) | `42` | A grant remains valid while a tail handler suspends its call |
| 5 | [existential mutation](05_state_and_collections/existential_mut.eld) | `1nat` | Erased owner facts survive factories, branches, early return and match forwarding |
| 5 | [existential projected mutation](05_state_and_collections/existential_projected_mut.eld) | `42` | Dynamic mutation through a parent projection preserves inner state |
| 5 | [list failure](05_state_and_collections/list_failure.eld) | `3nat` | Failed removal returns original collection |
| 5 | [finite loop](05_state_and_collections/finite_loop.eld) | `42` | Ownership-threaded finite iteration |
| 5 | [freeze](05_state_and_collections/freeze.eld) | `2nat` | Capture-free elements escape after freezing through a generic wrapper |
| 5 | [cleanup](05_state_and_collections/cleanup.eld) | `1` | `using` discharges a linear guard |
| 5 | [tail cleanup](05_state_and_collections/tail_cleanup.eld) | `42` | Clause-local early return cleans up before resumption |
| 6 | [capture rows](06_tasks/capture_rows.eld) | `42` | Affine callback captures survive spawn and consuming await |
| 6 | [join](06_tasks/join.eld) | `42` | Spawn and await |
| 6 | [inherited handler](06_tasks/inherited_handler.eld) | `42` | Same inherited handler, different child result types |
| 6 | [child-local handler](06_tasks/child_local_handler.eld) | `42` | Answer-changing handler inside a child |
| 6 | [library join](06_tasks/library_join.eld) | `42` | Higher-order task composition |
| 8 | [formatter semantics](08_formatting/semantics.eld) | `42` | Formatting retains field evaluation order, handler forwarding and precedence |

## Executable source fixtures

Run a fixture and the source tests from the repository root:

```sh
uv run python tools/run_eldude.py examples/07_source_pipeline/combined.eld
# 42
uv run python -m unittest discover -s tools -p 'test_source*.py' -v
```

These fixtures cover handler evidence, ownership, resumption, and cleanup through the [source pipeline](../tools/README.md#file-map). [test_source_pipeline.py](../tools/test_source_pipeline.py) asserts independent expected values and event ordering.

| Program | Result | Checked execution |
| --- | --- | --- |
| [branch](07_source_pipeline/branch.eld) | `42` | Conditional execution |
| [functions](07_source_pipeline/functions.eld) | `42` | Forward function reference, typed callback, closure capture |
| [tail cleanup](07_source_pipeline/tail_cleanup.eld) | `40` | Clause-local close precedes implicit resume and caller acquisition |
| [tail output](07_source_pipeline/tail_output.eld) | `()` | Operation returns `Int` even though handler output is `Unit` |
| [deep once](07_source_pipeline/once_deep.eld) | `99` | Two deep entries, one close of the frame resource, legal post-resume work |
| [nested normal return](07_source_pipeline/nested_return.eld) | `42` | Nested normal-return clauses resume the enclosing operation; deep re-entry closes one shared frame and preserves local cleanup |
| [operation arguments](07_source_pipeline/operation_arguments.eld) | `42` | Scalar arguments pass through source functions, forwarding and deep once resumption without becoming frame captures |
| [multiple operations](07_source_pipeline/multi_operations.eld) | `42` | Mixed modes, nested instances, selective forwarding and tail cleanup |
| [multiple operations with shared frame](07_source_pipeline/multi_operations_deep.eld) | `42` | Deep re-entry through different operations, one frame close, lexical normal-return resumption and complete sibling residual |
| [multiple operations with affine exit](07_source_pipeline/multi_operations_affine.eld) | `7` | Forwarded affine exit skips the later read, unwinds body cleanup and preserves an outside resource |
| [clause local](07_source_pipeline/clause_local.eld) | `()` | Local resource remains owned after resume, then closes |
| [affine scope](07_source_pipeline/affine_scope.eld) | `7` | Frame closes, captured body cleanup unwinds, outside resource closes afterward |
| [affine asynchronous cleanup](07_source_pipeline/affine_async.eld) | `()` | Abandonment triggers masked suspension and cleanup; body yield is skipped |
| [forwarding](07_source_pipeline/forwarding.eld) | `42` | Inner then outer dispatch, outer then inner resumption; outer residual slot retained |
| [callbacks](07_source_pipeline/callbacks.eld) | `20` | Fixed callback dispatches outer (`10`); ambient callback/source function dispatches inner (`20`) |
| [capture/trait integration](07_source_pipeline/capture_trait_integration.eld) | `42` | Callback capture rows through tuples, generic multi-trait dispatch and dynamic mutation; one explicit file close |
| [combined](07_source_pipeline/combined.eld) | `42` | Nested handlers, forwarding, deep once resumption and resource cleanup |

In `combined`, allocation identities are deterministic: frame `1`, protected body `2`, tail-clause temporary `3`, and post-resume locals `4` and `5`. The significant ordering is:

```text
acquire 1, 2
Step dispatch → resume → Step dispatch → resume
Read inner dispatch → Read outer dispatch
acquire 3 → cleanup 3 → resume outer(42) → resume inner(42)
explicit close 1
acquire 4 → cleanup 4 → acquire 5 → cleanup 5
cleanup 2
```

In `nested_return`, each `Step` clause installs a `Read` handler whose normal-return clause resumes `Step`. The trace orders cleanup of temporary `2` before the first `Step` resume, cleanup of temporary `3` before the second, then one explicit close of frame `1` and post-resume cleanup of locals `4` and `5`.

`operation_arguments` passes `7` and `42` through `request`, the inner forwarding `Echo`, and the outer `Echo` clause. Cleanup of each tail-clause temporary precedes the corresponding outer/inner/`Step` resumptions. The retained frame then closes once, followed by cleanup of the two post-resume locals.

In `multi_operations`, the order is inner `step` dispatch/resume, inner then outer `read` dispatch, acquisition/cleanup of temporary `2`, outer then inner tail resume, and cleanup of protected body `1`. The handler has separate `tail read(Int) -> Int`, `once step() -> Unit`, and `affine stop(Int) -> Unit` contracts.

In `multi_operations_deep`, named dispatch enters the shared outer `step`; its nested empty handler's normal return resumes that operation. Inner `step` resumes, then inner `read` forwards to the same outer frame. Tail cleanup precedes resumption, normal return closes frame `1` exactly once, and independent post-resume cleanup finishes afterward. The scalar `read(frame)` parameter shadows the retained frame resource without acquiring its ownership. An outward `Mark` effect from `read` forces the checker to validate the earlier `step` resume against the complete residual using fresh states.

In `multi_operations_affine`, after inner `step` resumes, inner `stop(7)` forwards to outer `stop`; both captured segments are abandoned, body resource `2` is cleaned, and outside resource `1` is explicitly closed. No read dispatch or read-clause temporary acquisition occurs.

See the [handler interpreter reference](../tools/README.md#handler-and-resumption-experiment) for dispatch event shapes.

## Fixture host profile

The `eldude::fixture` module provides simulated resources and suspension events for tests. Ordinary source modules are resolved separately. Import the names used by the file, with optional aliases:

```eldude
import eldude::fixture::{File, acquire as open, close};

fn consume(file: File) -> Unit { close(file) }
```

| Export | Contract | Simulation |
| --- | --- | --- |
| `File` | Linear, non-`Dup`, non-`Discard`; canonical cleanup `{}` | Owned token, no filesystem handle |
| `AsyncFile` | Linear; canonical cleanup `{suspend}` | Owned token with suspending cleanup |
| `acquire` | `fn() -> File` | Fresh token; `('acquire', 'File', id)` |
| `acquireAsync` | `fn() -> AsyncFile` | Fresh token; `('acquire', 'AsyncFile', id)` |
| `close` | `fn(File) -> Unit` | Consumes token; `('close', id, 'explicit')` |
| `closeAsync` | `fn(AsyncFile) ->{suspend} Unit` | Unmasked suspension event, then consuming close |
| `yield` | `fn() ->{suspend} Unit` | `('suspend', False)` |

Acquisition is pure in this simulated profile. `using` owns any acquired resource until consumption or scope exit. Multiple acquisitions evaluate left to right and cleanup runs right to left. Still-live `File` cleanup emits `('close', id, 'cleanup')`; `AsyncFile` cleanup first emits `('suspend', True)` to record its cancellation mask. Explicitly discharged tokens do not close again, although cleanup effects remain conservatively admitted by the static row. Within task groups, yield points also advance the cooperative scheduler and deliver pending cancellation. Resources remain simulated; no real I/O or foreign calls occur.

Fixture primitives must be called directly by their imported names/aliases. Use a source closure, such as `fn() => acquire()`, when passing one as a callback. There is no implicit prelude, and user declarations with these spellings execute their own checked bodies. Fixture type names also require imports. Ordinary source module loading and the cleanup implementations used by the examples execute; real resource management remains deferred.

Source annotations, operation arguments, forwarding, lexical resumption, and implementation limits are documented in the [implementation guide](../tools/README.md#source-to-execution-experiment).

## Rejection targets

`reject/syntax` must fail the grammar recognizer. `reject/semantics` must parse and reach its intended static failure; [test_source_semantic_examples.py](../tools/test_source_semantic_examples.py) checks these diagnostics, including all three existential capture cases. [Handler counterexamples](#enforced-source-rejections) are enforced separately below.

| Program | Required failure |
| --- | --- |
| [missing loop separator](reject/syntax/missing_loop_separator.eld) | Missing `;` after a nonfinal loop |
| [effect application](reject/syntax/effect_application.eld) | Expression type application needs `::<...>` |
| [multiple row tails](reject/syntax/multiple_row_tails.eld) | Only one tail may follow `\|` |
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

Run the [repository checks](../README.md#checks) to verify syntax failures, enforced semantic failures, and the documented implementation limits. The positive corpus command does not run rejection fixtures.

## Enforced source rejections

Each file below is valid normative syntax and is rejected during compilation, before `run` is called. Tests assert the reason, filename, line and column. Ownership diagnostics include related binding/transfer locations where applicable.

| Fixture under `reject/semantics/source_pipeline` | Required static failure |
| --- | --- |
| [wrong operation result](reject/semantics/source_pipeline/wrong_operation_result.eld) | `tail` supplies `Unit` to an `Int` operation |
| [tail resume](reject/semantics/source_pipeline/tail_resume.eld) | Explicit resume in a tail clause |
| [missing resume](reject/semantics/source_pipeline/missing_resume.eld) | Once clause completes without resuming |
| [repeated resume](reject/semantics/source_pipeline/repeated_resume.eld) | Second resume consumes an already-used capability |
| [escaping resume](reject/semantics/source_pipeline/escaping_resume.eld) | Nested closure cannot capture resumption |
| [frame transfer](reject/semantics/source_pipeline/frame_transfer.eld) | Frame resource used after transfer to resumption |
| [clause local](reject/semantics/source_pipeline/clause_local.eld) | Resumption does not dispose of a clause-local resource |
| [unsafe affine](reject/semantics/source_pipeline/unsafe_affine.eld) | Naked resource in abandoned segment |
| [skipped consumption](reject/semantics/source_pipeline/skipped_consumption.eld) | Affine completion could skip outside linear consumption |
| [skipped outer resume](reject/semantics/source_pipeline/skipped_outer_resume.eld) | Affine completion could skip enclosing once resumption |
| [outward pending](reject/semantics/source_pipeline/outward_pending.eld) | Outward affine operation could abandon a suspended once segment |
| [deep residual](reject/semantics/source_pipeline/deep_residual.eld) | Complete re-entered clause residual could abandon a local at resume |
| [post resume](reject/semantics/source_pipeline/post_resume.eld) | Outside obligation remains live after resume returns |
| [same family](reject/semantics/source_pipeline/same_family.eld) | Clause must name an outer instance explicitly |
| [nested return skips resume](reject/semantics/source_pipeline/nested_return_affine_skip.eld) | Affine completion could skip the normal-return clause's enclosing resume |
| [nested return repeats resume](reject/semantics/source_pipeline/nested_return_repeated.eld) | A resume after the nested handler reuses the same capability |
| [nested return frame transfer](reject/semantics/source_pipeline/nested_return_frame_transfer.eld) | The enclosing frame remains unavailable after resumption through a return clause |
| [nested return outward effect](reject/semantics/source_pipeline/nested_return_outward.eld) | Post-resume outward control still owes outside resource consumption |
| [nested return deep residual](reject/semantics/source_pipeline/nested_return_residual.eld) | Re-entered clauses may abandon a local held across normal-return resumption |

The argument fixtures under `reject/semantics/operation_arguments` are also valid grammar and fail before execution:

| Fixture | Required static failure |
| --- | --- |
| [type](reject/semantics/operation_arguments/type.eld) | `Unit` supplied to an `Int` parameter |
| [arity](reject/semantics/operation_arguments/arity.eld) | Missing operation argument |
| [clause arity](reject/semantics/operation_arguments/clause_arity.eld) | Missing clause parameter |
| [abandonment](reject/semantics/operation_arguments/abandonment.eld) | Argument evaluation may suspend while an unprotected resource remains live |

The 29 [multi-operation rejection fixtures](reject/semantics/multi_operations) cover incomplete/duplicate/unknown declarations and handler entries; call/clause arity and scalar types; mode-specific results; same-family sibling dispatch; explicit tail, missing/repeated once and escaping resumes; transferred frame use; undisposed clause locals; unsafe affine exit; skipped outside consumption/enclosing resume; post-resume outward abandonment; and argument effects. Each `/*error*/` marker immediately precedes the required diagnostic location; tests assert filename, offset, line, column and related ownership notes.

In particular, [sibling residual](reject/semantics/multi_operations/sibling_residual.eld) rejects the earlier resume because a sibling clause can perform an outward affine operation during deep re-entry. [Opaque family call](reject/semantics/multi_operations/opaque_affine_family.eld) rejects a source function call whose admitted family includes `affine`, even though its body currently invokes only `tail read`. These fail statically, before the interpreter runs.

For example:

```sh
uv run python tools/run_eldude.py examples/reject/semantics/source_pipeline/frame_transfer.eld
# .../frame_transfer.eld:9:19: semantic: file was already consumed
# ...:5:9: note: Binding declared here
# ...:8:13: note: Ownership transferred here
```

The [missing-semicolon fixture](reject/syntax/source_pipeline/missing_semicolon.eld) reports `syntax` and exits nonzero without executing. Additional tests cover unknown/duplicate names, malformed tokens, incorrect annotations, root evidence, named dispatch scope, and source/host contracts. The [code/test map](../tools/README.md#file-map) locates these checks and the underlying IR regressions.
