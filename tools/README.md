# Eldude implementation guide

[Documentation and project map](../docs/index.md) · [Setup and checks](../README.md#quick-start)

This guide describes the experimental Python implementation. The [language specification](../docs/language-specification.md) defines the intended language; passing the examples does not establish full conformance.

[File map](#file-map) · [Source support](#source-to-execution-experiment) · [Limits](#implementation-limits) · [Inference](#inference-experiment) · [Handlers](#handler-and-resumption-experiment)

## File map

Read the component and its tests for the task at hand. All tools use the Python standard library. Run the commands below from the repository root.

| File | Responsibility | Tests |
| --- | --- | --- |
| [run_eldude.py](run_eldude.py) | CLI, result display, corpus manifest validation | [Corpus runner](test_run_examples.py) |
| [check_docs.py](check_docs.py) | Local Markdown links/anchors, chapter/code map coverage, example table results | [Documentation checks](test_check_docs.py) |
| [check_grammar.py](check_grammar.py) | EBNF lexer/recognizer and Markdown/JSON generation | [Syntax](test_grammar.py), [publications](test_grammar_artifacts.py), [program/API corpus](test_grammar_programs.py) |
| [source_syntax.py](source_syntax.py) | Located AST, syntax errors, executable-subset parsing | [Core syntax](test_source_syntax.py), [extended syntax](test_source_extended_syntax.py) |
| [source_modules.py](source_modules.py) | Declared module identities, imports, dependency order | [Modules](test_source_modules.py) |
| [source_pipeline.py](source_pipeline.py) | Public compile/execute API, source diagnostics, shared handler lowering, annotation adapter | [Source pipeline and handler traces](test_source_pipeline.py) |
| [source_elaboration.py](source_elaboration.py) | Module/data elaboration, generics, trait/method resolution | [Values](test_source_values.py), [ownership and dispatch boundaries](test_source_ownership_boundaries.py) |
| [source_declarations.py](source_declarations.py) | Recursive bindings and ordered global initialization | [Declarations](test_source_declarations.py) |
| [source_features.py](source_features.py) | Data/control checking and execution, library primitives, source task integration | [Features](test_source_features.py), [integration regressions](test_source_feature_regressions.py), [semantic examples](test_source_semantic_examples.py), [source tasks](test_source_tasks.py) |
| [effect_rows.py](effect_rows.py) | Scoped-row equality and closed-row opening on resolved labels (§16.5) | [Row counterexamples](test_effect_rows.py) |
| [inference.py](inference.py) | Annotated expression IR, type/effect/capture inference, ownership | [Inference](test_inference.py) |
| [handlers.py](handlers.py) | Handler clause/resumption checks, evidence lowering, interpreter | [Handlers](test_handlers.py) |
| [task_runtime.py](task_runtime.py) | Per-execution cooperative scheduling, cancellation, group draining | [Scheduler](test_task_runtime.py), [source integration](test_source_tasks.py) |

The source path is `run_eldude` → `source_pipeline` → parsing/module loading → `source_elaboration` → checked expression IR → `handlers.run`. The checker layers are `SourceChecker` → `FeatureChecker` → `HandlerChecker` → `Checker`; source features and declarations also extend lowering and execution. The row solver operates on resolved labels and does not select handlers or check ownership.

## Source-to-execution experiment

The [positive corpus](../examples/README.md) executes through located parsing, checking, and interpretation. [manifest.json](../examples/manifest.json) owns expected results; the [fixture guide](../examples/README.md#executable-source-fixtures) describes handler traces and the [test host](../examples/README.md#fixture-host-profile).

### Supported forms and contracts

The executable subset includes `Int`/`Nat`/`Bool`/`Unit`, tuples, nominal records/enums, exhaustive matching, generic functions and effect instances, traits with associated types, methods, closures, branches, structural recursion, and numeric recursion admitted by `diverge`. Blocks support bindings, early returns, `Result` propagation, and local `try` scopes. Regions, `Ref`, `List`, `DynArray`, finite iteration, and user cleanup methods cover the state examples.

Module lookup uses declared identities in the source directory, optional search roots, and bundled `stdlib`. Functions support forward and recursive references; every body is checked, including unused and generic bodies. Globals initialize in deterministic dependency order and must be pure, terminating, duplicable, and discardable. Reading one before initialization produces a defect.

Functions require annotated parameters and signatures. Closures require parameter annotations but may infer result/effect contracts. Function types and closed effect rows are supported; omitted rows mean pure. Annotations cannot hide effects, replace a lambda's own contract, or erase whole-value capture bounds. Only empty source `captures {}` clauses are supported. Binding identities distinguish shadowed local and handler names; qualified references select module declarations.

Operands and record fields evaluate once in source order. Checked `Int64` arithmetic defects unwind active cleanup scopes. Generic bodies use conservative usage rules. Region and whole-value capture checks reject escaping state, including captures accumulated by mutable owners. `using` cleans up on normal completion and structural exits. Branches must agree on ownership consumption and resumption use.

### Source handlers

Handlers use the [evidence and resumption checks](#handler-and-resumption-experiment) below. Operation parameters and results support `Int`, `Unit`, `Bool`, `Nat`, and tuples, `Option`, `Result`, or enums whose contents recursively meet that data-only boundary. Resources and callbacks remain unsupported. For example, `effect Echo { tail echo(value: Int, marker: Unit) -> Int; }` declares two positional parameters. Arguments evaluate once, left to right, before dispatch; their effects and pending ownership obligations remain visible. Clauses bind fresh parameters from the declared types; `echo(value, _) => value;` discards the scalar second argument. Arity, types, duplicate names, and scope are checked. Scalar parameters remain usable after resume and are distinct from retained frame captures.

Operation identity includes both family and operation name; unrelated families can reuse a spelling. Every operation and unused clause is checked independently. A handler must cover every declaration with a clause or `forward name;`. One `forward ..;` covers only omitted operations and may coexist with explicit entries in any order. Empty families need no clauses. Duplicate/unknown declarations, clauses, or forwards are rejected. Unqualified same-family calls inside any clause are forbidden, including calls to a sibling operation; name an outer instance explicitly ([§26.4](../docs/language-spec/06-handlers.md#264-same-family-operations-inside-clauses)).

Effects and evidence identify family instances: operations on one instance share a slot. Forwarding preserves evaluated arguments and the outer slot. Direct dispatch uses the selected mode; ordinary calls and complete resumption residuals use the whole family's abandonment envelope, including affine siblings ([§17.3](../docs/language-spec/05-effects-and-failure.md#173-derived-continuation-control-envelope)). A naked resource cannot cross such a call just because its implementation currently invokes only a tail operation.

Nested normal-return clauses share the enclosing operation's lexical resumption capability and ownership state ([§25.1](../docs/language-spec/06-handlers.md#251-lexical-resumption)). Nested operation clauses introduce their own capability; nested functions cannot capture either. Resuming transfers non-`Dup` frame captures exactly once while outside obligations stay live. Inner affine completion that could skip an enclosing resume remains conservatively rejected. The [source rejections](../examples/README.md#enforced-source-rejections) cover repeated/skipped resume, frame reuse, clause-local obligations, outward abandonment, and complete sibling residuals.

### Tasks and host

Structured tasks provide lexical task groups, spawn, consuming await/cancel, group draining, and cooperative cancellation. Inherited handlers must preserve arbitrary child answers and have duplicable captures; child-local handlers may change answers. Each execution owns its scheduler.

The explicit `eldude::fixture` profile supplies simulated resource tokens and suspension events. Import each name used; user functions named `acquire` or `close` have their ordinary checked meanings. The [fixture host reference](../examples/README.md#fixture-host-profile) defines exports, event shapes, cleanup, and callback limitations.

### Entry point, API, and diagnostics

The runner calls an exported, nullary, nongeneric `main` returning `Int`, `Nat`, `Bool`, or `Unit`. This is a fixture convention, not a language entry-point rule. No unhandled algebraic slots may remain; intrinsic `suspend`/`diverge` may be admitted.

`compile_source(text, filename)` and `compile_file(path)` return `SourceProgram` with `ast`, `expression`, `program`, `inferred`, `functions`, and `handled_rows`. With `tools` on Python's import path, `handlers.run(checked.program)` returns `Execution.value` and `Execution.events`; `execute_file(path)` combines checking and execution. `Program.origins` maps lowered-node identities to source spans.

Parsing first checks full EBNF membership using the normative lexer's tokens, then builds a filename/span-bearing AST. `Grammar.lex` retains its token-pair API alongside `lex_spanned`. Malformed syntax reports `syntax`; valid syntax outside the subset reports `unsupported: Implementation limit`. `Diagnostic` carries a category, message, primary span, and related declaration/transfer spans. Single-file CLI diagnostics go to stderr with filename, line, and column and a nonzero exit. Static errors prevent execution; arithmetic defects terminate it after structural unwinding.

### Implementation limits

- Unsupported forms include existential trait objects (`any`), recursive record representations, guarded matches, untyped closure parameters, nonempty source capture clauses, resource/callback operation payloads, destructuring clause parameters, general foreign execution, and parts of the declared library API.
- Trait selection and structural termination checking cover a bounded subset. Multiple specialized method implementations for one nominal type report an implementation limit. General usage/control joins remain outside the experiment.
- Resources are simulated. The recursive cooperative scheduler starts children FIFO, resumes suspended children in stack order, and cannot wait on a suspended ancestor. It does not provide production I/O, parallelism, arbitrary dependency graphs, or unbounded recursion/suspension depth.

## Inference experiment

`tools/inference.py` checks a small expression IR built with Python tuples. Parameter types and callback usage guarantees are annotated; function result types, effect rows, whole-value result-capture bounds, and closure usage guarantees are inferred from bodies. Calls instantiate those contracts. The experiment reuses the existing row solver unchanged.

Run just the experiment:

```sh
uv run python -m unittest discover -s tools -p 'test_inference.py' -v
```

The cases exercise these outcomes:

| Case | Accepted result | Rejected boundary |
| --- | --- | --- |
| Effectful traversal | An annotated `Int ->{\| e} Unit` callback gives traversal the inferred row `{\| e}`; a logging callback instantiates it to `{Log}`. Repeated operations reuse one slot. | A callback owning a linear resource cannot satisfy traversal's `Dup + Discard` requirements. |
| Nested same-family handlers | An ambient callback selects the inner `Log`; a lexically named callback retains the outer instance. Removing the inner handler leaves the outer slot. | A closure retaining a named handler cannot escape its delimiter. |
| Scoped state | Reading a local `Ref<Int>` yields `Int`, an empty residual row, and no captures after leaving the region. | Returning the reference or a closure retaining it, or storing an inner closure in an outer cell, fails. |
| Cancellation with ownership | `using` protects a resource across `suspend`; suspending canonical cleanup is checked under its cancellation mask. | An unprotected resource, including a shadowed binding or an argument awaiting later argument evaluation, cannot cross a potentially abandoning call. Masking does not neutralize an affine cleanup effect. |
| Imported `DynArray::freeze` wrapper | The wrapper's contract is inferred, serialized, and loaded into a fresh checker without its body. Instantiating it at `Int` gives a capture-free `List<Int>` that can leave the allocation region. | A list of references to an outer region still retains the inner array's whole bound and cannot leave it. This is the deliberate precision cost of [§13.6](../docs/language-spec/04-captures-and-access.md#136-canonical-interfaces-and-conservative-mutation). |

A combined case traverses a list, mutates a local cell, handles logging, and suspends while a resource is protected by `using`. It returns `Int` with only `{suspend}` and no retained captures.

One-tail rows and whole-value bounds still require handler-instance selection, lexical scope checks, ownership tracking, retention horizons, and callback capture/usage compatibility. Callback weakening is allowed at direct argument boundaries; this prototype conservatively requires invariant contracts inside data constructors and callback parameter positions. Nested functions use distinct internal provenance sources before exporting `arg:N`/environment bounds, and ownership is tracked by binding identity across shadowing.

The base inference fragment has scalar/aggregate expressions, conservative conditional joins, monomorphic local regions, finite traversal of discardable elements, and tail-handler delimiters. Primitive and imported contracts are trusted inputs; JSON round-tripping demonstrates separate checking, not complete canonical-interface validation. That checker has no Eldude parsing, handler-clause/resumption checking, scheduler, task model, general loop inference, trait solving, higher-rank inference, `NonAbandoning` constraint inference, general `mut`-grant checking, or generic retention-horizon solving. Unknown effect tails are treated as potentially abandoning. These experiments do not prove soundness or measure compiler/runtime performance.

## Handler and resumption experiment

`tools/handlers.py` extends the inference checker with operation clauses and normal-return clauses. `compile_program(expression, operations=...)` checks the annotated IR and produces a `Program` containing its inferred result and lowered `core`. `run(program)` executes that core and returns its value and an event trace. Dispatch nodes refer to explicit `Evidence` keys; ordinary calls supply an evidence argument. Closures capture lexically fixed evidence and receive ambient evidence at invocation.

```sh
uv run python -m unittest discover -s tools -p 'test_handlers.py' -v
```

| Case | Checked and executed behavior | Rejected boundary |
| --- | --- | --- |
| `tail` | The clause supplies the operation result even when the handler output differs. Clause-local `using` cleanup finishes before implicit resumption. | Incorrect operation results and explicit `resume`. |
| `once` | Deep re-entry shares one resource obligation; the normal-return clause closes it once. Code after `resume` executes with non-`Dup` frame captures unavailable. | Missing/repeated resumptions, escaping capabilities, reusing transferred captures, and leaving clause-local resources undisposed. |
| `affine` | Zero resumption unwinds the captured body's `using` scopes, including masked asynchronous cleanup, while outside resources remain available. The clause discharges its own frame captures. | Naked resources in the captured segment, and nested affine completion that could skip linear consumption or an enclosing resumption. |
| Forwarding | Inner dispatch targets outer evidence and resumes the inner computation with the outer operation result. The outer slot remains in the inner residual row. | Unqualified same-family operation syntax in a clause; outward abandonment of an unsafe suspended segment. |

The counterexamples also check two less visible obligations. A resumed computation admits the **complete handler residual**, including effects introduced by re-entered operation clauses. The checker collects the handled body, normal-return clause and every operation clause into that row, then rechecks every clause with fresh ownership and resumption states. Resume adds the supplied residual, and both conditional branches are checked; a stabilization check rejects any row growth after validation. Separately, resources outside the handler remain live after resumption returns; outward control from post-resume code must account for them. Clause-local resources and handler-frame captures have distinct ownership states.

Explicit evidence selects instances; single-use continuations implement the three modes without duplicating resource obligations. Residual effects, suspended segments, and ownership are checked together above the shared row solver.

The experiment supports multiple operations per family and clauses with conservative conditional joins. Operation contracts use the data types described under [source handlers](#source-handlers); handler results are checked separately against the clauses and body. `Operation(mode, result, parameters=())` declares the positional contract. The annotated IR uses `E('perform_args', family, tuple_of_argument_expressions, *named_instance)` and `E('clause', parameter_names, body)` for parameterized dispatch/clauses; existing nullary `E('perform', family, *named_instance)` and plain clause bodies still work. The executable subset covers scalar/aggregate expressions, bindings, closures/calls, resource acquisition/close, `using`, suspension events, and handlers/resumptions. It conservatively requires non-`Dup` frame captures to remain available until transfer and rejects affine changes needing general usage joins. An opaque `tail`/`once` continuation is treated as non-discardable when a clause attempts outward abandonment. These are prototype restrictions, not new language rules.

`operations=` also accepts named tables such as `{'Read': {'value': Operation('tail', INT, (INT,)), 'tick': Operation('once', UNIT)}}`. `E('perform_op', family, operation_name, argument_tuple, *named_instance)` selects a contract explicitly. `E('handle_ops', family, instance_name, body, named_clause_tuple, returning)` supplies `(operation_name, clause_ir)` entries; each clause uses the existing `clause`/`forward` forms. All clauses and normal return share one logical frame, distinct from each invocation's scalar parameters and clause-local resources. Legacy `{'Read': Operation(...)}` inputs, `perform`, `perform_args` and single-clause `handle` remain supported for singleton families; ambiguous legacy forms are rejected. `Program.operations` contains normalized per-family tables (a legacy unnamed signature uses the `None` key).

Multi-operation dispatch events extend the existing tuple by appending the operation name: `('dispatch', family, instance_name, operation_name)`. Singleton dispatch events retain `('dispatch', family, instance_name)`, and resume/abandon/cleanup event shapes are unchanged. Evaluated argument payloads and operation identity survive every forwarding and continuation wrapper. Direct and generated forwarding dispatch nodes retain source origins.

In the base handler experiment, resources are simulated ownership tokens; `yield` and masked asynchronous cleanup emit events without scheduling or delivering cancellation. The source frontend extends this same checker and interpreter. Return/loop elaboration, generic families, task execution, and imported source execution are supplied by the source extensions in the file map; they are outside the base handler fragment. Resource/callback operation payloads and `self` recursion remain outside that fragment. The interpreter uses recursive Python continuation closures, including for `tail`; it does not demonstrate optimized tail lowering or production runtime performance.
