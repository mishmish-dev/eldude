# Capture and existential completeness implementation plan

> **For agentic workers:** Use `superpowers:executing-plans` to implement this plan task by task. Steps use checkbox (`- [x]`) syntax for tracking. The tasks share checker contracts; execute them in order.

**Goal:** Remove the six capture and existential implementation restrictions, with working Eldude programs demonstrating every new feature.

**Architecture:** Extend the existing source → checked IR → interpreter path. Share capture substitution and trait-constraint checking across static calls and erased calls; preserve whole-value provenance and access authority through both. Reuse the parser, example runner, and standard-library host integration.

**Tech stack:** Python 3.14.8 or newer, standard library only, Eldude source fixtures, `unittest`.

**Spec:** [Types and ownership](language-spec/02-types-and-ownership.md) (§§6, 9), [traits](language-spec/03-traits.md) (§§10–11), [captures and access](language-spec/04-captures-and-access.md) (§§12–15), [canonical interfaces](language-spec/12-interfaces-and-tooling.md) (§72). Use the [code/test map](../tools/README.md#file-map) to find the current implementation.

**Status:** Implementation and acceptance programs are complete through task 8; final whole-branch review and verification are in progress. The task programs are runnable in the example corpus.

## Global constraints

- **Programs first:** create the task's `.eld` programs, record independent expected results, and run them before changing the implementation. A positive program must parse, check, and execute; each rejection must reach its intended semantic check. Python-level tests supplement this evidence.
- Keep positive programs in `examples/manifest.json` and the matching `examples/README.md` tables. Temporary `pending` entries may document a failing baseline; a completed task has none of its programs pending, skipped, or expected to report `unsupported`.
- Preserve specification section numbers and anchors. Change normative prose only where a contract needs clarification; update implementation claims after verification.
- Capture expressions use finite, idempotent unions. Result-capture upper bounds do not establish ownership or permission to duplicate/discard a value. Preserve whole-argument bounds through aggregates, erasure, mutation, and `await`.
- Keep language-level dynamic-compatibility rules: ordinary receiver required, no method-local generics, no raw concrete `Self` outside the receiver, no GAT projections in the dynamic interface. Unresolved ordinary associated projections must be fixed or reduced using visible contracts.
- Reject genuinely ambiguous region inference and invalid constraints. Removing an implementation restriction must not turn these into guessed solutions.
- Add no dependency, parallel execution framework, general borrow syntax, or new interface-file format. Extend existing `Fn.dumps` / `Fn.loads` metadata as needed.

## Review focus

| Failure mode | Required evidence |
| --- | --- |
| Nested functions reuse parameter names; serialization changes their meaning | Factory and shadowing programs plus alpha-renaming/round-trip checks in task 1 |
| A generic or erased value loses usage requirements or implementation prerequisites | Linear callbacks in task 2; visible and missing evidence in tasks 4–5 |
| Trait arguments or method names collide in cached interfaces | Two instantiations in both declaration orders in task 5; distinct-trait name collision in task 6 |
| A helper hides regional captures in a result, task, or mutated owner | Original three capture rejection programs throughout; combined program and exit-path cases in task 8 |
| A grant expires during suspension or silently acquires another owner's authority | Projected access, independent regions, and handler suspension programs in tasks 7–8 |

## Order and completion criteria

| Task | Restriction addressed | Depends on |
| --- | --- | --- |
| 1. Parameter-dependent capture contracts | A returned callable cannot name the function's own parameters | Existing concrete captures |
| 2. Capture-row polymorphism | `captures {..C}` and capture-row usage bounds | 1 |
| 3. Region inference and explicit arguments | Valid multi-region callback calls cannot be resolved | 1–2 |
| 4. Shared trait constraints | Missing general prerequisite and associated-equation checking | 1–3 |
| 5. Instantiated existential interfaces | Generic traits, associated bindings, trait/method/impl `where` clauses | 4 |
| 6. Multiple trait packages | More than one ordinary trait in `any` | 5 |
| 7. Mutable access foundations | Missing owner/grant semantics needed by dynamic `mut` | 1–4 |
| 8. Dynamic mutable dispatch | `mut self` in a dynamically compatible interface | 5–7 |

Each task ends with its programs working, focused checks passing, updated support documentation, and a reviewable change. Commit task changes separately when executing the plan; preserve unrelated work already in the checkout.

## Files and shared interfaces

| File | Planned responsibility |
| --- | --- |
| `tools/capture_rows.py` (new), `tools/test_capture_rows.py` (new) | Scoped capture terms, substitution, equality/inclusion constraints; keep separate from effect rows, whose algebra differs |
| `tools/trait_constraints.py` (new), `tools/test_trait_constraints.py` (new) | Canonical trait heads, evidence selection, prerequisite checks, associated-equation normalization |
| `tools/inference.py`, `tools/source_pipeline.py` | Callable contracts, usage, region/capture instantiation, owner and grant checking |
| `tools/source_syntax.py`, `tools/source_elaboration.py`, `tools/source_declarations.py` | Preserve generic binder kinds/order, resolve source contracts, validate declarations and dynamic interfaces |
| `tools/source_features.py`, `tools/handlers.py` | Checked package dictionaries, access projection, dynamic calls and runtime storage |
| `tools/test_source_capture_contracts.py`, `tools/test_source_semantic_examples.py` | Execute acceptance files; assert metadata, events, and precise rejection diagnostics |
| `tools/test_source_ownership_boundaries.py`, `tools/test_source_feature_regressions.py`, `tools/test_source_tasks.py` | Existing access, mutation, handler, and task regression coverage |
| `stdlib/collections/dyn_array.eld`, `stdlib/README.md`, `docs/standard-library.md` | Declare and document the minimum projection API used in tasks 7–8 |
| `examples/`, `tools/README.md`, `docs/index.md` | Programs, expected results, supported-subset claims, and navigation |

Keep the new modules limited to those two shared semantic responsibilities. Do not reorganize the checker hierarchy as part of this work.

## Task 1: Parameter-dependent capture contracts

**Files:** `capture_rows.py`, `inference.py`, `source_pipeline.py`, `source_elaboration.py`; their tests from the file map above.

**Interface:** Represent a capture expression as a finite set of scoped provenance/argument/environment atoms. `substitute_captures(expr, substitutions)` replaces whole sources with whole capture expressions without capturing another function's binders. Keep callable-environment captures separate from `Fn.bound`, the whole-result upper bound.

- [x] Create `examples/02_ownership/parameter_capture.eld`: `make(file: File) -> fn() -> Unit captures {file}` returns a closure that closes the file. Its `main` invokes the closure and returns `42`; assert exactly one acquire and one explicit close event.
- [x] Create `examples/05_state_and_collections/parameter_capture.eld`: a factory returns a reader whose signature names its `cell` parameter; nested factories reuse that name and read distinct cells. Assert the combined result is `42`.
- [x] Create `examples/reject/semantics/parameter_capture_twice.eld` and `parameter_capture_escape.eld`: invoking the returned linear closure twice rejects reuse; returning a local-region reader rejects region escape. Run all four files to record the current failures.
- [x] Resolve function parameters before capture clauses nested in the result type. Bind capture names to identities and positional sources, preserving the captured values' usage obligations independently of provenance bounds. Use the same substitution in calls, nested callable types, aggregates, and source annotations.
- [x] Extend `Fn.dumps` / `Fn.loads` to preserve nested binder scopes, environment captures, and result bounds. Verify alpha-renamed signatures have equivalent canonical contracts; retain existing trusted-IR compatibility.
- [x] Run the task's positive programs and source tests; require `42`, the exact cleanup trace, and both intended rejection diagnostics. Remove the parameter-dependent implementation-limit assertion only after these pass.

## Task 2: Capture-row polymorphism and usage bounds

**Files:** task 1 files, `source_declarations.py`, `source_features.py`, `test_capture_rows.py`, `test_source_capture_contracts.py`.

**Interface:** Extend capture terms with declared row variables. `CaptureSolver.equal(left, right)` and `CaptureSolver.include(actual, allowed)` collect constraints; `solve()` returns substitutions and residual obligations. Generic-body variables remain rigid; each call gets fresh variables. Row usage obligations are checked separately from capture-set inclusion.

- [x] Create `examples/02_ownership/capture_rows.eld`: generic `defer<..C>` returns its callback with the same captures; a constrained repeat helper calls a duplicable callback twice to produce `42`. Also relay and invoke a callback owning a `File` exactly once, verifying its close event.
- [x] Create `examples/05_state_and_collections/affine_capture_row.eld`: relay a callback retaining a `DynArray`, invoke it once, and return `42`. This exercises a discardable, nonduplicable environment.
- [x] Create `examples/reject/semantics/capture_row_duplicate.eld` and `capture_row_discard.eld`: a file-owning callback fails `..C: Dup` and `..C: Discard`, respectively. Run these files before implementation; neither may finish as an `unsupported` test.
- [x] Bind `..C`, retain it in callable contracts, and implement idempotent union substitution and equality/inclusion solving. Preserve unresolved obligations when several substitutions are possible; do not choose an arbitrary provenance atom or reuse effect-row multiset rules.
- [x] Check `where ..C: Dup + Discard` in generic bodies and instantiated calls. Recompute callable permissions from actual retained obligations; carry substitutions through returned callbacks, trait signatures, aggregates, and task results.
- [x] Execute the programs and focused tests. Add solver checks for duplicate atoms, empty rows, repeated variables, rigid variables, and conflicting usage obligations. Replace the capture-row implementation-limit test with these executable guarantees.

## Task 3: Joint region inference and explicit generic arguments

**Files:** `source_syntax.py`, `source_elaboration.py`, `inference.py`, `source_pipeline.py`; `test_source_extended_syntax.py`, `test_source_capture_contracts.py`.

**Interface:** Preserve the ordered generic binder list and each binder's kind in callable contracts. Call instantiation combines explicit arguments with constraints from parameter/result types, effects, and capture expressions before solving remaining region variables.

- [x] Create `examples/05_state_and_collections/inferred_regions.eld`: two-region callbacks whose input/result types and state effects determine their region arguments return `42`; reversing independent call-site constraints leaves the result unchanged.
- [x] Create `examples/05_state_and_collections/explicit_regions.eld`: use `::<@outer, @inner>` to resolve an otherwise ambiguous callback call, and pass an explicit capture-row argument using existing grammar. Return `42`.
- [x] Create `examples/reject/semantics/ambiguous_callback_regions.eld`, `generic_argument_kind.eld`, and `generic_argument_scope.eld`. Require ambiguity, wrong-kind, and out-of-scope diagnostics; supplement these with a wrong-arity source case. Record failures before changing inference.
- [x] Replace the single-unmatched-region shortcut with joint constraint collection and unique-solution inference. Keep region identities invariant; do not introduce lifetime subtyping or pick the first region encountered.
- [x] Elaborate explicit generic arguments by declared kind instead of treating every argument as a type. Preserve binder order through substitution and serialization; report unresolved choices at the call with the explicit-argument remedy.
- [x] Run the new programs and tests in both declaration/argument constraint orders. Keep the ambiguous program rejected while the explicit and uniquely inferable variants execute.

## Task 4: Shared trait constraints and associated equations

**Files:** `trait_constraints.py`, `source_elaboration.py`, `source_declarations.py`, `inference.py`; `test_trait_constraints.py`, `test_source_semantic_examples.py`.

**Interface:** `select_impl(goal, evidence)` selects a canonical full trait head (receiver plus trait arguments) and returns the substitution and required evidence. `normalize_type(type, evidence)` applies admitted associated equations and returns the normalized type with any obligations. Static and dynamic checking must use these same operations.

- [x] Create `examples/02_ownership/trait_prerequisites.eld`: a generic wrapper implementation uses a smaller element prerequisite and explicit caller evidence; a method using a normalized associated result returns `42`.
- [x] Create `examples/reject/semantics/trait_missing_prerequisite.eld`, `trait_overlap.eld`, and `trait_constraint_cycle.eld`. Require missing evidence, overlapping heads even when prerequisites differ, and nondecreasing/cyclic obligations. Record these failures first.
- [x] Canonicalize aliases and full heads, including all binder kinds. Check parameter coverage, kind correctness, and occurs checks. Reject overlap using heads alone; select with one-way matching that instantiates implementation variables, never unknown caller types. Prefer exact local evidence and postpone unresolved goals.
- [x] Enforce the prerequisite decrease and variable-occurrence rules in §10.7, including trait-bound expansion and its cycle check. Keep intrinsic `Dup`, `Discard`, and `NonAbandoning` judgments outside user implementation search. Reject implementation methods with stronger requirements than their trait contracts.
- [x] Normalize associated equations using §10.8's decrease rules, binding kinds, and prerequisite propagation. Keep unresolved abstract projections opaque; never solve backwards from a desired associated result.
- [x] Execute the positive and rejection files. Add targeted equation/occurs-check tests and a source rejection for a stronger implementation-method prerequisite; preserve existing coverage and associated-type mismatch tests.

## Task 5: Generic and associated-type existential interfaces

**Files:** task 4 files, `source_pipeline.py`, `source_features.py`, `handlers.py`; `test_source_capture_contracts.py`.

**Interface:** Replace the trait-name-only package/cache identity with the canonical instantiated bound, associated bindings, and usage promises. Dynamic method contracts come from that visible interface; packaging stores checked implementation evidence and dispatch targets, without exposing the hidden type.

- [x] Create `examples/02_ownership/existential_arguments.eld`: package two instantiations of one generic trait, invoke both methods, and return `42`. Execute with both declaration orders to catch incomplete cache keys.
- [x] Create `examples/02_ownership/existential_associated.eld`: fix `Item=Int` in an existential interface, call a method returning `Self::Item`, and return `42`.
- [x] Create `examples/02_ownership/existential_constraints.eld`: exercise trait-level, method-level, and implementation `where` prerequisites with visible evidence, including an explicit usage promise; return `42`.
- [x] Create `examples/reject/semantics/existential_hidden_prerequisite.eld` and `existential_unfixed_associated.eld`: hidden concrete facts cannot make an invalid visible interface callable, and an unresolved associated type cannot leak into dispatch. Run every file before lifting existing guards.
- [x] Instantiate trait parameters and associated bindings through the shared solver. Audit every declared generic category (§6.3): types, constructors, regions, effect rows, capture rows, and natural indices. Add a minimal `.eld` instantiation per category to the argument program and wire missing kind handling; a type-only implementation does not complete this task. Preserve first-order head restrictions rather than adding arithmetic or higher-rank inference.
- [x] Validate `DynCompatible` after visible substitutions/normalization. Discharge interface prerequisites from package-visible contracts; discharge implementation prerequisites when packaging. Preserve usage and provenance during dispatch, forwarding, and usage weakening. Keep method-local generics, raw `Self`, missing receivers, and GAT projections rejected.
- [x] Execute all new files, existing erasure programs, and the original whole-argument/await capture rejections. Replace generic/associated/constraint implementation-limit tests with acceptance cases and real boundary errors.

## Task 6: Multiple ordinary traits in one package

**Files:** `docs/language-spec/03-traits.md`, `source_elaboration.py`, `source_features.py`, `handlers.py`; `test_source_capture_contracts.py`, `test_source_semantic_examples.py`.

**Contract clarification:** The grammar already accepts multiple applied bounds, while §11 primarily describes one ordinary trait. Record this proposed clarification in §11 before implementation: every bound describes the same hidden value; dictionaries remain keyed by canonical trait and member; duplicate identical bounds normalize; conflicting equations and unqualified collisions between distinct trait members reject. Weakening may remove promises/bounds while preserving the remaining evidence and ownership obligations. Do not invent qualified-call syntax as part of this task.

- [x] Create `examples/02_ownership/existential_traits.eld`: one value implements two traits with distinct method names; `any First + Second + Discard` dispatches both, then weakens to one bound, returning `42`.
- [x] Create `examples/reject/semantics/existential_member_collision.eld` and `existential_conflicting_bindings.eld`. Pin the diagnostic for ambiguous unqualified member lookup and contradictory bindings for the same associated member. Run the files first.
- [x] Canonicalize the set of full trait bounds and validate all of them against one hidden value. Reuse task 5's interface instantiation and evidence. Resolve methods using the stored trait/member identity, including inside handler clauses and recursive call-graph analysis.
- [x] Preserve whole-value captures and linear obligations through repackaging; dropping a bound must never imply `Dup`, `Discard`, or capture freedom. Execute the acceptance programs and usage/region rejection variants.

## Task 7: Mutable owners and call-scoped grants

**Files:** `inference.py`, `source_pipeline.py`, `source_features.py`, `handlers.py`, `stdlib/collections/dyn_array.eld`; access tests and library docs from the file map.

**Interface:** Attach intrinsic mutable-owner identity/region facts to checked values. A grant records the parent owner, authorized region, target path, access mode, and active call interval. Forwarding and projection derive authority from the supplied grant; runtime operations target the original storage.

- [x] Create `examples/05_state_and_collections/forwarded_mut.eld`: forward a `mut` parameter through two helpers, change the same array, and return its length `1`.
- [x] Create `examples/05_state_and_collections/projected_mut.eld`: call the planned `DynArray::withMut` API from §15.2 on an array containing another array. Push `42` into the inner array using its existing API and explicit inner-region effect, then retrieve that value through `pop` and return it. Exercise the missing-index path with a discardable callback; verify that the callback is not invoked.
- [x] Create `examples/reject/semantics/mut_alias_conflict.eld`, `mut_grant_escape.eld`, and `mut_wrong_authority.eld`: reject overlapping access during argument evaluation, a captured/returned grant, and mutation of an independent nested owner without its required authority. Add `mut_root_effect.eld`: a function owning an array forms a root grant to an empty-row helper but omits the required state effect from its own contract. Run these before implementation.
- [x] Implement intrinsic owner facts and grant formation once in the shared call checker. Nonduplicability alone cannot establish `MutableOwner`; a linear `File` is not a mutable root. Charge root `state<@r>` even when the written callee row is empty.
- [x] Route existing mutable primitives and source calls through the same grant tracking. Preserve parent authority for forwarded/projected grants, including projections of values whose own region differs. Keep explicit row effects and independently accessed `Ref`/nested-owner effects; never subtract them as an optimization.
- [x] Declare and execute `withMut` using existing collection/runtime integration. Its callback is checked under the supplied projection grant, with `Discard` required for a possible lookup miss. Avoid implementing unrelated projection APIs here.
- [x] Add a source program with handler suspension during an active grant; ensure the interval remains active until the call ends. Check normal, early-return, recoverable-error, and cancellation paths for release/cleanup, with rejection programs for conflicting access. Run access, handler, and task regression tests.

## Task 8: Dynamic mutable dispatch and integration

**Files:** task 7 files, `source_elaboration.py`, `source_declarations.py`; capture/access/handler/task tests from the file map.

**Interface:** A dynamic `mut self` call consumes a valid call-scoped grant to the package's original hidden storage. Owner facts, whole-value capture bounds, and dictionary contracts survive packaging, call returns, joins, and existing interface serialization.

- [x] Create `examples/05_state_and_collections/existential_mut.eld`: implement a `Grow<@r>` trait for `DynArray<Int,@r>`; dynamic `grow(mut self, ...)` calls the existing push primitive and `len(view self)` observes length `1` on the same package. Both trait methods explicitly admit `state<@r>`. Name the trait method `grow` to keep primitive dispatch distinct.
- [x] Create `examples/05_state_and_collections/existential_projected_mut.eld`: invoke `Grow<@inner>` through `withMut` on a package stored in an outer-region array. Supply the declared inner-state effect, verify the package now has length `1`, and return `42`. The method must be valid for the supplied parent grant; it cannot use outer-region authority to erase its independent inner-state requirement.
- [x] Create `examples/reject/semantics/existential_mut_nonowner.eld` and `existential_mut_capture_escape.eld`: reject forming a root grant from a nonowner and retaining inner-region data through a dynamic mutation returning `Unit`. Record the failing baseline first.
- [x] Enable dynamic `mut` interfaces using task 7's access path and task 5's checked evidence. Pass original storage/grants through runtime dictionaries. Preserve conservative mutation bounds on every continuing exit, including recoverable failures and handler-mediated exits; retain `Ref`'s fixed retention horizon.
- [x] Create `examples/07_source_pipeline/capture_trait_integration.eld`: relay a capture-polymorphic callback through a helper, use a generic existential with a fixed associated type and two trait bounds, mutate through dynamic access, then invoke the callback to return `42`. Assert observable state and cleanup events independently of the checker.
- [x] Add cross-feature source cases for a mutated erased owner surviving a branch, a recoverable failure, and a handler exit. Run `whole_argument_capture.eld`, `await_whole_argument_capture.eld`, and `mut_capture_escape.eld`; all must still reject at their existing ownership/lifetime checks.
- [x] Remove only the six restrictions now demonstrated by these programs from `tools/README.md`. Document remaining unrelated subset limits and the permanent DynCompatible requirements accurately. Complete the checks below before claiming this milestone works.

## Verification and handoff

Run a new positive program directly as it is developed:

```sh
uv run python tools/run_eldude.py examples/02_ownership/parameter_capture.eld
uv run python -m unittest discover -s tools -p 'test_source_capture_contracts.py' -v
uv run python -m unittest discover -s tools -p 'test_source_semantic_examples.py' -v
```

The positive command must print its manifest value. Semantic rejection tests must assert the expected diagnostic category/message and source location, not merely that compilation raised an exception. Use the existing source fixture adapter for rejection programs without an exported entry point. Host cleanup and handler events are asserted through the existing source execution API.

At each task boundary, update example expectations, the code map if files were added, and supported-subset prose, then run the [root checks](../README.md#checks):

```sh
uv run python tools/check_docs.py
uv run python tools/check_grammar.py
uv run python -m unittest discover -s tools -p 'test_*.py'
uv run python tools/run_eldude.py --examples --strict
git diff --check
```

Completion means all tests pass, the positive corpus has zero unsupported/failed examples, and rejection programs fail for their intended reason. Report the program paths, expected and actual outputs, relevant event assertions, and any remaining implementation limits. Passing Python-only tests or changing an expected result to match the implementation cannot substitute for making the Eldude programs work.
