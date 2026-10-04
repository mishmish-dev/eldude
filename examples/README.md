# Eldude implementation targets

All **49 positive examples** execute through the source checker and interpreter, with their original source and expected results. Each file is a separate program. The harness calls its exported `main`; this is a corpus convention, not a language entry-point rule. Task examples run in a cooperative scheduler owned by each execution.

```sh
uv run python tools/run_eldude.py --examples --strict
# 49 passed, 0 unsupported, 0 failed
```

[manifest.json](manifest.json) records independently specified expected values for every positive file. Corpus execution fails for wrong values, unexpected diagnostics, missing manifest entries, or regressions. `--strict` also rejects pending implementation limits; there are currently none in this corpus. Rejection fixtures are checked separately by the test suite.

| Stage | Runnable | Capabilities exercised |
| --- | ---: | --- |
| Values | 9 / 9 | Arithmetic, closures, generics, records, tuples, enums and startup |
| Ownership | 5 / 5 | Linear nominal types, inspection, recursion and traits |
| Results | 3 / 3 | Library imports, matching, `?` and `try` |
| Effects | 6 / 6 | Generic instances, handlers, forwarding and `Result` payloads |
| State and collections | 6 / 6 | Regions, collection primitives, iteration and cleanup traits |
| Tasks | 4 / 4 | Cooperative scheduling, task groups, spawn/await and library join |
| Source pipeline | 16 / 16 | Handler evidence, ownership, resumption and cleanup regressions |

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

`reject/syntax` must fail the grammar recognizer. `reject/semantics` must parse; the source pipeline enforces the new `source_pipeline` counterexamples below. The older targets in this table also reject; the runner remains a bounded implementation, so rejection does not establish complete language conformance.

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
uv sync --locked
uv run python tools/check_grammar.py
uv run python -m unittest discover -s tools -p 'test_*.py'
```

## Executable source fixtures

Run the complete source milestone from the repository root:

```sh
uv run python tools/run_eldude.py examples/07_source_pipeline/combined.eld
# 42
uv run python -m unittest discover -s tools -p 'test_source*.py' -v
```

All these files execute real Eldude syntax through a located AST, declaration resolution, the existing checked expression IR, explicit handler evidence and the existing interpreter. `tools/test_source_pipeline.py` asserts literal expected values and event ordering; it does not infer expectations from the implementation.

| Program | Result | Checked execution |
| --- | --- | --- |
| [literal](01_values/literal.eld) | `42` | Existing scalar fixture |
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

`uv run python tools/run_eldude.py examples/07_source_pipeline/nested_return.eld` also prints `42`. Each `Step` clause installs a `Read` handler whose normal-return clause resumes `Step`. The trace orders cleanup of temporary `2` before the first `Step` resume, cleanup of temporary `3` before the second, then one explicit close of frame `1` and post-resume cleanup of locals `4` and `5`.

`uv run python tools/run_eldude.py examples/07_source_pipeline/operation_arguments.eld` prints `42`. It passes `7` and `42` through `request`, the inner forwarding `Echo`, and the outer `Echo` clause. Cleanup of each tail-clause temporary precedes the corresponding outer/inner/`Step` resumptions. The retained frame then closes once, followed by cleanup of the two post-resume locals.

`uv run python tools/run_eldude.py examples/07_source_pipeline/multi_operations.eld` prints `42`. Its order is inner `step` dispatch/resume, inner then outer `read` dispatch, acquisition/cleanup of temporary `2`, outer then inner tail resume, and cleanup of protected body `1`. The handler has separate `tail read(Int) -> Int`, `once step() -> Unit`, and `affine stop(Int) -> Unit` contracts.

`multi_operations_deep.eld` also prints `42`. Named dispatch enters the shared outer `step`; its nested empty handler's normal return resumes that operation. Inner `step` resumes, then inner `read` forwards to the same outer frame. Tail cleanup precedes resumption, normal return closes frame `1` exactly once, and independent post-resume cleanup finishes afterward. The scalar `read(frame)` parameter shadows the retained frame resource without acquiring its ownership. An outward `Mark` effect from `read` forces the checker to validate the earlier `step` resume against the complete residual using fresh states.

`multi_operations_affine.eld` prints `7`. After inner `step` resumes, inner `stop(7)` forwards to outer `stop`; both captured segments are abandoned, body resource `2` is cleaned, and outside resource `1` is explicitly closed. No read dispatch or read-clause temporary acquisition occurs.

For families with several operations, dispatch events are `('dispatch', family, instance, operation)`. Singleton families retain the previous three-field dispatch events. Other event shapes are unchanged.

The broader [forwarding](04_effects/forwarding.eld) now executes unchanged using checked arithmetic. [Tail result](04_effects/tail_result.eld) still needs `Result`/matching/`?`, and [tail cleanup](05_state_and_collections/tail_cleanup.eld) needs regions/traits/references/early return. The smaller fixtures above do not redefine those programs.

## Fixture host profile

The runner provides exactly one built-in module profile, `eldude::fixture`. It is a test host contract, not a standard-library implementation or arbitrary imported-code loader. Import only the names required by the file, with optional aliases:

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

Source functions have annotated parameters and signatures; closures require parameter annotations but may infer their result/effect contract. Function types and closed effect rows are supported; omitted rows mean pure. Annotations cannot hide effects, replace a lambda's own contract, or erase whole-value capture bounds. Only empty source `captures {}` clauses are currently supported. Local and handler names have distinct binding identities across shadowing; qualified references to this file's module select its declarations.

Effect declarations may specify positional `Int`/`Unit` parameters, for example `effect Echo { tail echo(value: Int, marker: Unit) -> Int; }`. Call arguments evaluate once, left to right, before dispatch. A clause such as `echo(value, _) => value;` binds fresh local parameters using the declaration's types; `_` discards a scalar argument. Parameter arity, types, duplicate names and scope are checked. Both named calls and `forward operation;`/`forward ..;` preserve evaluated arguments and instance evidence. Clause parameters remain available after resume when their scalar types allow duplication; they do not replace retained frame obligations. Resource/callback operation parameters and destructuring clause patterns are implementation limits.

Operation names are scoped to their family; unrelated families may reuse a spelling with different signatures. Every operation is independently checked, including clauses not reached at runtime. A handler must cover all declarations with operation clauses or explicit `forward name;` entries. A single `forward ..;` covers only omitted operations and may coexist with explicit entries in any order. Empty families need no operation clauses. Unknown or duplicate operations, duplicate explicit entries and duplicate fallback forwards are rejected. A clause cannot dispatch unqualified to another operation of its own family; name an outer instance explicitly. Effect slots still belong to family instances, so forwarding preserves the outer slot without re-evaluating arguments.

Direct dispatch applies the selected operation's mode. Ordinary calls admitting the family and complete resumption residuals retain the conservative abandonment envelope of all declared operations, including affine siblings. A naked resource cannot cross such a call merely because its available implementation currently calls only a tail operation. Every resumption includes outward effects from all sibling clauses, with fresh ownership states for validation. Frame captures transfer once and never return to post-resume ownership; clause-local resources must be discharged separately. General usage/control joins remain outside this experiment.

The runner requires exported nullary, nongeneric `main` returning `Int`, `Nat`, `Bool` or `Unit`, with only intrinsic effects left at the root. Other functions, including unused and generic bodies, are checked before execution. All capabilities in the stage table above now execute. Branches must agree on ownership consumption and resumption use. Arithmetic defects unwind active `using` scopes, including through handlers. See the [root README](../README.md#source-to-execution-experiment) for the remaining language, library and scheduler limits.

Normal-return clauses preserve the enclosing operation's lexical resumption, including through multiple nested handlers ([§25.1](../docs/language-spec/06-handlers.md#251-lexical-resumption)). Nested operation clauses instead use their own capability; explicit tail resume and capture by a nested function remain semantic errors. The checker shares the enclosing capability's used state and frame ownership, so a resume inside a normal-return clause counts toward exactly-once checking and transferred frame captures remain unavailable afterward. Inner affine handlers that could skip that resume are conservatively rejected, just as when the resume occurs in their body.

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

The complete suite checks the corpus manifest, scalar operations, branches, generic calls, record/tuple ownership, defect cleanup, and all previous pipeline regressions. The **133 grammar productions** remain unchanged and synchronized.

For example:

```sh
uv run python tools/run_eldude.py examples/reject/semantics/source_pipeline/frame_transfer.eld
# .../frame_transfer.eld:9:19: semantic: file was already consumed
# ...:5:9: note: Binding declared here
# ...:8:13: note: Ownership transferred here
```

The [missing-semicolon fixture](reject/syntax/source_pipeline/missing_semicolon.eld) reports `syntax` and exits nonzero without executing. The [branch fixture](07_source_pipeline/branch.eld), previously an implementation-limit check, now prints `42`. [Task join](06_tasks/join.eld) now prints `42`. Tests additionally cover unknown/duplicate names, malformed tokens, incorrect annotations, root evidence, named dispatch scope and source/host call contracts. Existing Python IR tests remain regressions for the broader inference and handler experiments.
