# Eldude implementation guide

[Documentation and project map](index.md) · [Setup and checks](../README.md#quick-start)

This guide describes the experimental Python implementation. The [language specification](language-specification.md) defines the intended language; passing the examples does not establish full conformance.

[File map](#file-map) · [Source support](#source-to-execution-experiment) · [Limits](#implementation-limits) · [Inference](#inference-experiment) · [Handlers](#handler-and-resumption-experiment)

## File map

Read the component and its tests for the task at hand. The package uses only the Python standard library at runtime. Run the commands below from the repository root.

| File | Responsibility | Tests |
| --- | --- | --- |
| [__init__.py](../src/eldude/__init__.py), [__main__.py](../src/eldude/__main__.py) | Python package and module entry point; wheel bundles grammar and library resources | [Package installation](../tests/test_packaging.py) |
| [core/__init__.py](../src/eldude/core/__init__.py), [source/__init__.py](../src/eldude/source/__init__.py), [runtime/__init__.py](../src/eldude/runtime/__init__.py), [tooling/__init__.py](../src/eldude/tooling/__init__.py) | Subpackage boundaries; initializers keep imports independent | [Package installation](../tests/test_packaging.py) |
| [core/model.py](../src/eldude/core/model.py) | Shared source spans, diagnostics, AST records, binding identities, and checked-source result | [Syntax records](../tests/source/test_syntax.py), [artifact execution without the frontend](../tests/test_packaging.py) |
| [core/types.py](../src/eldude/core/types.py) | Type substitution, compatibility, joins, and pattern binding names | [Inference](../tests/core/test_inference.py), [trait constraints](../tests/core/test_traits.py), [feature regressions](../tests/source/test_feature_regressions.py) |
| [core/declarations.py](../src/eldude/core/declarations.py) | Recursive bindings and ordered global initialization | [Declarations](../tests/source/test_declarations.py) |
| [core/rows.py](../src/eldude/core/rows.py) | Scoped-row equality and closed-row opening on resolved labels (§16.5) | [Row counterexamples](../tests/core/test_rows.py) |
| [core/captures.py](../src/eldude/core/captures.py) | Finite capture unions and scoped whole-argument substitution (§13) | [Capture rows](../tests/core/test_captures.py) |
| [core/traits.py](../src/eldude/core/traits.py) | Full trait heads, one-way evidence selection, prerequisite checks and associated normalization (§10) | [Trait constraints](../tests/core/test_traits.py) |
| [core/inference.py](../src/eldude/core/inference.py) | Annotated expression IR, type/effect/capture inference, ownership | [Inference](../tests/core/test_inference.py) |
| [core/handlers.py](../src/eldude/core/handlers.py) | Handler clause/resumption checks, evidence lowering, interpreter | [Handlers](../tests/core/test_handlers.py) |
| [source/grammar.py](../src/eldude/source/grammar.py) | EBNF lexer, recognizer/concrete trees, and Markdown/JSON generation | [Syntax](../tests/source/test_grammar.py), [publications](../tests/source/test_grammar_artifacts.py), [program/API corpus](../tests/source/test_grammar_programs.py) |
| [source/syntax.py](../src/eldude/source/syntax.py) | Located AST, syntax errors, executable-subset parsing | [Core syntax](../tests/source/test_syntax.py), [extended syntax](../tests/source/test_extended_syntax.py) |
| [source/modules.py](../src/eldude/source/modules.py) | Declared module identities, imports, dependency order | [Modules](../tests/source/test_modules.py) |
| [source/pipeline.py](../src/eldude/source/pipeline.py) | Public check/compile/execute API and runtime defect diagnostics | [Source API](../tests/source/test_pipeline.py) |
| [source/lowering.py](../src/eldude/source/lowering.py) | Base AST expression lowering and checked-feature lowering to handler IR | [Source handler contracts](../tests/source/test_handlers.py), [handler corpus and traces](../tests/source/test_handler_fixtures.py); shared [source assertions](../tests/source/support.py) |
| [source/checking.py](../src/eldude/source/checking.py) | Written annotation checking, capture preservation, and effect diagnostic origins | [Source API](../tests/source/test_pipeline.py), [capture contracts and erasure](../tests/source/test_capture_contracts.py) |
| [source/type_elaboration.py](../src/eldude/source/type_elaboration.py) | Source types, generics, associated types, trait interfaces, and effect/capture contracts | [Values](../tests/source/test_values.py), [capture contracts and erasure](../tests/source/test_capture_contracts.py) |
| [source/elaboration.py](../src/eldude/source/elaboration.py) | Module declaration collection, source control/data expressions, and compilation orchestration | [Values](../tests/source/test_values.py), [ownership and dispatch boundaries](../tests/source/test_ownership_boundaries.py) |
| [source/features.py](../src/eldude/source/features.py) | Data/control checking, library primitive contracts, and source task checking | [Features](../tests/source/test_features.py), [integration regressions](../tests/source/test_feature_regressions.py), [semantic examples](../tests/source/test_semantic_examples.py), [source tasks](../tests/source/test_tasks.py) |
| [runtime/artifact.py](../src/eldude/runtime/artifact.py) | Deterministic checked-IR encoding, located decoding and bundled Python host entry | [Full corpus IR round trips and artifacts](../tests/tooling/test_build.py) |
| [runtime/features.py](../src/eldude/runtime/features.py) | Runtime data values, pattern matching, library primitive execution, structural exits, and source tasks | [Handler corpus and cleanup traces](../tests/source/test_handler_fixtures.py), [features](../tests/source/test_features.py), [source tasks](../tests/source/test_tasks.py), [built artifacts](../tests/tooling/test_build.py) |
| [runtime/tasks.py](../src/eldude/runtime/tasks.py) | Per-execution cooperative scheduling, cancellation, group draining | [Scheduler](../tests/runtime/test_tasks.py), [source integration](../tests/source/test_tasks.py) |
| [tooling/cli.py](../src/eldude/tooling/cli.py) | Unified project commands, selection, safe creation/formatting, metadata and JSON diagnostics; installed through [project scripts](../pyproject.toml) | [Project CLI](../tests/tooling/test_cli.py) |
| [tooling/model.py](../src/eldude/tooling/model.py) | Strict manifests, semantic versions, workspace ownership, pins and source boundaries | [Project model](../tests/tooling/test_model.py) |
| [tooling/resolver.py](../src/eldude/tooling/resolver.py) | Path graph resolution, atomic TOML locks and package-scoped imports | [Resolver and import boundaries](../tests/tooling/test_resolver.py) |
| [tooling/build.py](../src/eldude/tooling/build.py) | Experimental Python root validation, IR artifacts, zipapps and isolated execution | [Artifact and execution acceptance](../tests/tooling/test_build.py) |
| [tooling/run.py](../src/eldude/tooling/run.py) | CLI, result display, corpus manifest validation | [Single-file CLI](../tests/tooling/test_run.py), [corpus runner](../tests/tooling/test_examples.py) |
| [tooling/format.py](../src/eldude/tooling/format.py) | Syntax-directed source formatting, comment retention, check/write CLI | [Formatting, semantic round trips, and CLI](../tests/tooling/test_format.py) |
| [tooling/check_docs.py](../src/eldude/tooling/check_docs.py) | Local Markdown links/anchors, chapter/code map coverage, example table results | [Documentation checks](../tests/tooling/test_check_docs.py) |

The source path is `tooling.run` → `source.pipeline` → parsing/module loading → `source.elaboration` → checked expression IR → `core.handlers.run`. The project CLI supplies explicit module candidates and package import permissions to the same path. The checker layers are `SourceChecker` → `FeatureChecker` → `HandlerChecker` → `Checker`; source features and declarations also extend lowering and execution. The row solver operates on resolved labels and does not select handlers or check ownership.

`eldude.source.pipeline` is the public source API. It imports the frontend directly; compiler
components do not import the API back. Elaboration layers are `SourceElaborator`
→ `TypeElaborator` → `Elaborator`, separating module orchestration, type/contracts,
and base expression lowering. Shared records and type helpers live below these
layers. Runtime values and execution are separate from the source checker, so
checked-IR zipapps do not bundle or import the parser, module loader, or source
elaborators. The IR artifact format and source API signatures remain unchanged. Python imports
now use the subpackage paths in the file map; command names remain `eldude`,
`eldude-run`, and `eldude-format`.

The Python implementation remains one distribution with one version and no runtime
dependencies. A uv workspace with separate runtime/compiler/tooling distributions
would add package metadata and release boundaries without distinct dependency or
installation needs today. Revisit that split when a component needs independent
installation or release; module boundaries do not require workspace members.

The package root contains only `__init__.py` and `__main__.py`. Components are
organized into four subpackages, mirrored by test directories:

| Package / tests | Owns |
| --- | --- |
| `core/` | Shared IR/source records, types, inference, rows, traits, handlers, declarations |
| `source/` | Grammar, parser, module loading, elaboration, checking, lowering, source API |
| `runtime/` | Feature execution, task scheduling, checked-IR artifacts |
| `tooling/` | CLI, projects, builds, formatting, runners, documentation checks |

The root `unittest discover -s tests` command descends into these test packages.
`tests/source/support.py` supplies source assertions without discoverable cases;
`tests/test_packaging.py` checks the installed distribution. Source API, handler
contracts, corpus traces, and CLI behavior retain separate suites.

The formatter takes a separate path through the normative grammar's concrete
tree, preserving source details the executable AST discards. After `uv sync`, `eldude.tooling.format.format_source(text, filename='<source>')` returns
formatted source or raises a located `Diagnostic`. It accepts the full ordinary
source grammar, keeps author-written contracts unchanged, and verifies token and
comment preservation before returning. See the [design and style rules](formatter.md)
and [CLI commands](../README.md#format-source). It does not canonicalize generated
semantic interfaces; those require resolved semantic identities under §77.

## Project tooling

The [project commands](../README.md#project-cli) implement the foundation of the
[tooling design](tooling-design.md), plus the explicitly experimental
`python::experimental` application/test host. `cli::standard`, native hosts, embeddings, cross
compilation, remote dependency resolution, full semantic interfaces, and interface
cache invalidation remain separate delivery work and are not implied by these commands.

The path resolver locks the full owning workspace, including its members' development
dependencies. Consumers ignore dependency development pins, locks, and test dependencies.
Source selection keeps test and production import environments separate, indexes
declared module identities, and rejects duplicate providers and filesystem paths that
cross source or package boundaries. Selected roots can check despite unrelated body
errors. Libraries need no entry or host, but declaration/generic-body checks retain
the existing supported-subset limits.

Python builds serialize checked IR with a versioned, explicit record whitelist.
This artifact format is neither a canonical semantic interface nor a public ABI.
Bundled interpreter code executes the stored IR in a subprocess, with source origins
retained for defects. Application output is inherited by `run`; machine-mode tests
capture labeled stdout/stderr events. The Python host currently has no Eldude argument
or production I/O API. The two profiles preserve the same evaluator behavior.

Build products use atomic replacement and identity-safe internal paths. Application
filenames include their content digest, so concurrent invocations can launch their
own products; deleting `build/` affects no source semantics. Repeated identical builds
preserve unchanged artifacts. This is artifact reuse only: every invocation still
checks source closures, without downstream semantic reuse or complete separate
compilation. Build records include toolchain/compiler identity, Python version,
resolved graph, host, machine target, and profile; there are no native inputs.

`check`, `build`, and `test --message-format=json` emit version-1 newline-delimited
events and a scoped summary. Diagnostics share their source messages with terminal
output, using zero-based half-open Unicode scalar offsets and one-based lines/columns.
Source/root rejection exits 1; configuration, unsupported capabilities, and operational
or internal tool failures exit 2. Formatting syntax failures also exit 2. Tests report
runner counts and failures, including empty selection, and application execution
returns the application's status.

## Source-to-execution experiment

The [positive corpus](../examples/README.md) executes through located parsing, checking, and interpretation. [manifest.json](../examples/manifest.json) owns expected results; the [fixture guide](../examples/README.md#executable-source-fixtures) describes handler traces and the [test host](../examples/README.md#fixture-host-profile).

### Supported forms and contracts

The executable subset includes `Int`/`Nat`/`Bool`/`Unit`, tuples, nominal records/enums, exhaustive matching, generic functions and effect instances, traits with associated types, methods, closures, branches, structural recursion, and numeric recursion admitted by `diverge`. Blocks support bindings, early returns, `Result` propagation, and local `try` scopes. Regions, `Ref`, `List`, `DynArray`, finite iteration, and user cleanup methods cover the state examples.

Module lookup uses declared identities in the source directory, optional search roots, and bundled `stdlib`. User functions support forward and recursive references; their bodies are checked, including unused and generic bodies. Bundled library function and implementation bodies are skipped: supported APIs use checker/runtime primitives or handwritten lowering, including `task::join2`. The [library status table](../stdlib/README.md) distinguishes these operations from declaration-only APIs. Globals initialize in deterministic dependency order and must be pure, terminating, duplicable, and discardable. Reading one before initialization produces a defect.

Functions require annotated parameters and signatures. Closures require parameter annotations but may infer result/effect contracts. Function types and closed effect rows are supported; omitted rows mean pure. Closed capture clauses may name lexical values, handler instances, or regions: `captures {file}`, `captures {outer}`, `captures {@r}`. Returned callable contracts may name their defining function's parameters. Capture-row parameters (`..C`) support callback forwarding and independent `where ..C: Dup + Discard` usage bounds, including inherited trait and implementation contracts. Explicit generic arguments preserve the declared type, constructor, region, effect-row, capture-row and natural binder order. Trait selection expands aliases, checks full heads and prerequisites, and validates decreasing associated equations. Effect-row `NonAbandoning` bounds use the intrinsic control judgment. Callable usage follows the named values' ownership, and annotations cannot hide effects or retained obligations. Root mutable access requires an intrinsic owner and charges its regional state even for an empty-row helper. Forwarding and `DynArray::withMut` preserve grant authority and original storage; nested mutable identities retain their declared effects. Callable-environment captures remain separate from whole-value result bounds, including through higher-order calls and serialization. See [explicit ownership captures](../examples/src/02_ownership/explicit_captures.eld) and [regional callbacks](../examples/src/05_state_and_collections/captured_callback.eld). Binding identities distinguish shadowed local and handler names; qualified references select module declarations.

Explicit `any Trait` annotations package values with instantiated trait bounds, fixed associated types, and optional `+ Dup` / `+ Discard` guarantees. Packaging checks full trait arguments, associated bindings, implementation prerequisites, and usage promises. Interface prerequisites must follow from visible contracts. Packaging preserves the hidden value's captures and intrinsic owner facts, and supplies runtime method dispatch. Dynamic mutable calls use the same grants and original storage as concrete calls; owner facts survive call returns and continuing branch joins. Bare packages remain linear. The supported interface has consuming, `view`, or `mut` receivers, no method generics, and no concrete `Self` outside the receiver. Existing packages may explicitly weaken their usage guarantees. See [existential dispatch](../examples/src/02_ownership/existentials.eld); the [capture rejection cases](../examples/README.md#rejection-targets) exercise whole-argument, await, and mutable-owner retention through erasure.

Operands and record fields evaluate once in source order. Checked `Int64` arithmetic defects unwind active cleanup scopes. Generic bodies use conservative usage rules. Region and whole-value capture checks reject escaping state, including captures accumulated by mutable owners. `using` cleans up on normal completion and structural exits. Branches must agree on ownership consumption and resumption use.

### Source handlers

Handlers use the [evidence and resumption checks](#handler-and-resumption-experiment) below. Operation parameters and results support `Int`, `Unit`, `Bool`, `Nat`, and tuples, `Option`, `Result`, or enums whose contents recursively meet that data-only boundary. Resources and callbacks remain unsupported. For example, `effect Echo { tail echo(value: Int, marker: Unit) -> Int; }` declares two positional parameters. Arguments evaluate once, left to right, before dispatch; their effects and pending ownership obligations remain visible. Clauses bind fresh parameters from the declared types; `echo(value, _) => value;` discards the scalar second argument. Arity, types, duplicate names, and scope are checked. Scalar parameters remain usable after resume and are distinct from retained frame captures.

Operation identity includes both family and operation name; unrelated families can reuse a spelling. Every operation and unused clause is checked independently. A handler must cover every declaration with a clause or `forward name;`. One `forward ..;` covers only omitted operations and may coexist with explicit entries in any order. Empty families need no clauses. Duplicate/unknown declarations, clauses, or forwards are rejected. Unqualified same-family calls inside any clause are forbidden, including calls to a sibling operation; name an outer instance explicitly ([§26.4](language-spec/06-handlers.md#264-same-family-operations-inside-clauses)).

Effects and evidence identify family instances: operations on one instance share a slot. Forwarding preserves evaluated arguments and the outer slot. Direct dispatch uses the selected mode; ordinary calls and complete resumption residuals use the whole family's abandonment envelope, including affine siblings ([§17.3](language-spec/05-effects-and-failure.md#173-derived-continuation-control-envelope)). A naked resource cannot cross such a call just because its implementation currently invokes only a tail operation.

Nested normal-return clauses share the enclosing operation's lexical resumption capability and ownership state ([§25.1](language-spec/06-handlers.md#251-lexical-resumption)). Nested operation clauses introduce their own capability; nested functions cannot capture either. Resuming transfers non-`Dup` frame captures exactly once while outside obligations stay live. Inner affine completion that could skip an enclosing resume remains conservatively rejected. The [source rejections](../examples/README.md#enforced-source-rejections) cover repeated/skipped resume, frame reuse, clause-local obligations, outward abandonment, and complete sibling residuals.

### Tasks and host

Structured tasks provide lexical task groups, spawn, consuming await/cancel, group draining, and cooperative cancellation. Inherited handlers must preserve arbitrary child answers and have duplicable captures; child-local handlers may change answers. Each execution owns its scheduler.

The explicit `eldude::fixture` profile supplies simulated resource tokens and suspension events. Import each name used; user functions named `acquire` or `close` have their ordinary checked meanings. The [fixture host reference](../examples/README.md#fixture-host-profile) defines exports, event shapes, cleanup, and callback limitations.

### Entry point, API, and diagnostics

The runner calls an exported, nullary, nongeneric `main` returning `Int`, `Nat`, `Bool`, or `Unit`. This is a fixture convention, not a language entry-point rule. No unhandled algebraic slots may remain; intrinsic `suspend`/`diverge` may be admitted.

`compile_source(text, filename)` and `compile_file(path)` return `SourceProgram` with `ast`, `expression`, `program`, `inferred`, `functions`, and `handled_rows`. After `uv sync`, `eldude.core.handlers.run(checked.program)` returns `Execution.value` and `Execution.events`; `execute_file(path)` combines checking and execution. `Program.origins` maps lowered-node identities to source spans.

`check_source(text, filename)` and `check_file(path)` return the same checked-program
shape with a `Unit` terminal expression instead of a fixture entry call. They check
user declarations and initializers without executing them; bundled library bodies
remain excluded as described above. Optional `sources` and
`import_allowed` inputs constrain discovery to the project's package graph. Existing
fixture compilation/execution APIs retain their entry convention.

Parsing first checks full EBNF membership using the normative lexer's tokens, then builds a filename/span-bearing AST. `Grammar.lex` retains its token-pair API alongside `lex_spanned`. Malformed syntax reports `syntax`; valid syntax outside the subset reports `unsupported: Implementation limit`. `Diagnostic` carries a category, message, primary span, and related declaration/transfer spans. Single-file CLI diagnostics go to stderr with filename, line, and column and a nonzero exit. Static errors prevent execution; arithmetic defects terminate it after structural unwinding.

### Implementation limits

- Callback-only region inference requires an unambiguous correspondence or explicit region arguments; ambiguous solutions reject rather than choosing a region. Dynamic interfaces retain the language restrictions on ordinary receivers, method-local generics, raw `Self`, and generic associated types.
- Other unsupported forms include recursive record representations, guarded matches, untyped closure parameters, resource/callback operation payloads, destructuring clause parameters, general foreign execution, and parts of the declared library API.
- Trait selection and structural termination checking cover a bounded subset. Multiple specialized method implementations for one nominal type report an implementation limit. General usage/control joins remain outside the experiment.
- Resources are simulated. The recursive cooperative scheduler starts children FIFO, resumes suspended children in stack order, and cannot wait on a suspended ancestor. It does not provide production I/O, parallelism, arbitrary dependency graphs, or unbounded recursion/suspension depth.

## Inference experiment

`src/eldude/core/inference.py` checks a small expression IR built with Python tuples. Parameter types and callback usage guarantees are annotated; function result types, effect rows, whole-value result-capture bounds, and closure usage guarantees are inferred from bodies. Calls instantiate those contracts. The experiment reuses the existing row solver unchanged.

Run just the experiment:

```sh
uv run python -m unittest discover -s tests -p 'test_inference.py' -v
```

The cases exercise these outcomes:

| Case | Accepted result | Rejected boundary |
| --- | --- | --- |
| Effectful traversal | An annotated `Int ->{\| e} Unit` callback gives traversal the inferred row `{\| e}`; a logging callback instantiates it to `{Log}`. Repeated operations reuse one slot. | A callback owning a linear resource cannot satisfy traversal's `Dup + Discard` requirements. |
| Nested same-family handlers | An ambient callback selects the inner `Log`; a lexically named callback retains the outer instance. Removing the inner handler leaves the outer slot. | A closure retaining a named handler cannot escape its delimiter. |
| Scoped state | Reading a local `Ref<Int>` yields `Int`, an empty residual row, and no captures after leaving the region. | Returning the reference or a closure retaining it, or storing an inner closure in an outer cell, fails. |
| Cancellation with ownership | `using` protects a resource across `suspend`; suspending canonical cleanup is checked under its cancellation mask. | An unprotected resource, including a shadowed binding or an argument awaiting later argument evaluation, cannot cross a potentially abandoning call. Masking does not neutralize an affine cleanup effect. |
| Imported `DynArray::freeze` wrapper | The wrapper's contract is inferred, serialized, and loaded into a fresh checker without its body. Instantiating it at `Int` gives a capture-free `List<Int>` that can leave the allocation region. | A list of references to an outer region still retains the inner array's whole bound and cannot leave it. This is the deliberate precision cost of [§13.6](language-spec/04-captures-and-access.md#136-canonical-interfaces-and-conservative-mutation). |

A combined case traverses a list, mutates a local cell, handles logging, and suspends while a resource is protected by `using`. It returns `Int` with only `{suspend}` and no retained captures.

One-tail rows and whole-value bounds still require handler-instance selection, lexical scope checks, ownership tracking, retention horizons, and callback capture/usage compatibility. Callback weakening is allowed at direct argument boundaries; this prototype conservatively requires invariant contracts inside data constructors and callback parameter positions. Nested functions use distinct internal provenance sources before exporting `arg:N`/environment bounds, and ownership is tracked by binding identity across shadowing.

The base inference fragment has scalar/aggregate expressions, conservative conditional joins, monomorphic local regions, finite traversal of discardable elements, and tail-handler delimiters. Primitive and imported contracts are trusted inputs; JSON round-tripping demonstrates separate checking, not complete canonical-interface validation. That checker has no Eldude parsing, handler-clause/resumption checking, scheduler, task model, general loop inference, trait solving, higher-rank inference, `NonAbandoning` constraint inference, general `mut`-grant checking, or generic retention-horizon solving. Unknown effect tails are treated as potentially abandoning. These experiments do not prove soundness or measure compiler/runtime performance.

## Handler and resumption experiment

`src/eldude/core/handlers.py` extends the inference checker with operation clauses and normal-return clauses. `compile_program(expression, operations=...)` checks the annotated IR and produces a `Program` containing its inferred result and lowered `core`. `run(program)` executes that core and returns its value and an event trace. Dispatch nodes refer to explicit `Evidence` keys; ordinary calls supply an evidence argument. Closures capture lexically fixed evidence and receive ambient evidence at invocation.

```sh
uv run python -m unittest discover -s tests -p 'test_handlers.py' -v
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
