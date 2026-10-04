# Eldude implementation targets

These small `.eld` programs are staged implementation targets. All positive files are syntax-checked; the literal example and the [source fixtures below](#executable-source-fixtures) also run through the bounded source checker and interpreter. Each positive file is a separate program. The fixture harness calls its exported `main` and compares the returned value; `main` is a corpus convention, not a new language entry-point rule. Task examples still need a future root supporting scheduling and `suspend`.

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

`reject/syntax` must fail the grammar recognizer. `reject/semantics` must parse; the source pipeline enforces the new `source_pipeline` counterexamples below. The older targets in this table retain their required failures; syntax acceptance alone does not establish their semantic rejection, and unsupported source features may prevent this prototype reaching those checks.

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

The existing broader [forwarding](04_effects/forwarding.eld), [tail result](04_effects/tail_result.eld) and [tail cleanup](05_state_and_collections/tail_cleanup.eld) are unchanged. Multiple operations/arithmetic, `Result`/matching/`?`, and regions/traits/references/early return remain their future targets. The smaller fixtures above do not redefine those programs.

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

Acquisition is pure in this simulated profile. `using` owns any acquired resource until consumption or scope exit. Multiple acquisitions evaluate left to right and cleanup runs right to left. Still-live `File` cleanup emits `('close', id, 'cleanup')`; `AsyncFile` cleanup first emits `('suspend', True)` to record its cancellation mask. Explicitly discharged tokens do not close again, although cleanup effects remain conservatively admitted by the static row. No actual suspension, cancellation delivery, I/O or foreign calls occur.

Fixture primitives must be called directly by their imported names/aliases. Use a source closure, such as `fn() => acquire()`, when passing one as a callback. There is no implicit prelude, and user declarations with these spellings execute their own checked bodies. Fixture type names also require imports. Ordinary module loading, generic cleanup/trait solving and real resource management are deferred.

Source functions have annotated parameters and signatures; closures require parameter annotations but may infer their result/effect contract. Function types and closed effect rows are supported; omitted rows mean pure. Annotations cannot hide effects, replace a lambda's own contract, or erase whole-value capture bounds. Only empty source `captures {}` clauses are currently supported. Local and handler names have distinct binding identities across shadowing; qualified references to this file's module select its declarations.

The runner requires exported nullary `main` returning `Int` or `Unit`, with only intrinsic effects left at the root. This is a fixture convention. Other functions, including unused functions, are checked before execution. General operators (beyond signed integer literals), branches, loops, recursion, open rows/generics, operation arguments, multiple operations, non-scalar handler results, early returns, nonempty capture annotations, top-level `let`, `self`, traits, regions and tasks produce explicit implementation-limit diagnostics.

The existing checker also does not thread an enclosing once/affine resumption through a nested handler's normal-return clause. That lexical use is valid under §25.1 but reports `unsupported`; it must not be confused with capturing a resumption in a nested function, which is a semantic error.

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

For example:

```sh
uv run python tools/run_eldude.py examples/reject/semantics/source_pipeline/frame_transfer.eld
# .../frame_transfer.eld:9:19: semantic: file was already consumed
# ...:5:9: note: Binding declared here
# ...:8:13: note: Ownership transferred here
```

The [missing-semicolon fixture](reject/syntax/source_pipeline/missing_semicolon.eld) reports `syntax`. The valid [branch fixture](07_source_pipeline/unsupported/branch.eld) reports `unsupported: Implementation limit`. Both exit nonzero without executing. Tests additionally cover unknown/duplicate names, malformed tokens, incorrect annotations, root evidence, named dispatch scope and source/host call contracts. Existing Python IR tests remain regressions for the broader inference and handler experiments.
