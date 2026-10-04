# Eldude

Eldude is a programming-language design with an experimental implementation. This repository contains its design contracts, a grammar recognizer, a bounded source-to-execution pipeline, staged example programs, and an initial standard-library API.

Release **0.0.5** adds the first source-to-execution pipeline, implementing a subset of the unchanged Eldude **0.0.4** language contract.

- [Documentation](docs/index.md): start here for the manifesto and documentation guide.
- [Language specification](docs/language-specification.md): twelve chapters, reader and implementer paths, and stable section links.
- [Formal grammar](docs/formal-grammar.md): generated presentation of [eldude.ebnf](docs/eldude.ebnf), also published as [JSON](docs/eldude-grammar.json).
- [Example programs](examples/README.md): incremental `.eld` implementation targets and expected outcomes.
- [Standard-library API](stdlib/README.md) and [profile](docs/standard-library.md): initial declarations, ownership contracts, and implementation priorities.
- [Effect-row prototype](tools/effect_rows.py): scoped-row equality and closed-row opening on resolved labels, with [counterexample tests](tools/test_effect_rows.py).
- [Expression inference experiment](tools/inference.py): effectful traversal, nested handlers, scoped state, cancellation checks, and imported capture contracts, with [executable cases](tools/test_inference.py).
- [Handler experiment](tools/handlers.py): clause checking, ownership across resumption, explicit evidence lowering, and a small interpreter, with [accepted programs and counterexamples](tools/test_handlers.py).
- [Source pipeline](tools/source_pipeline.py): located parsing, declaration resolution, contract checking, and execution of the [source fixtures](examples/README.md#executable-source-fixtures).

The repository's Python tools share a uv project pinned to Python 3.14.8 and use only the standard library. Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then check grammar publications, source syntax, and the prototypes:

```sh
uv sync --locked
uv run python tools/check_grammar.py
uv run python -m unittest discover -s tools -p 'test_*.py'
uv run python tools/run_eldude.py examples/07_source_pipeline/combined.eld
git diff --check
```

After editing the normative EBNF or the parsing/interface clauses in the [foundations](docs/language-spec/01-foundations.md) and [interfaces](docs/language-spec/12-interfaces-and-tooling.md) chapters, regenerate the standalone grammar Markdown and JSON with `uv run python tools/check_grammar.py --write`. The specification chapters are inputs and are not rewritten. Grammar acceptance alone does not establish type correctness or execute a program. The source runner checks and executes the subset below; this is not a production compiler or runtime.

## Source-to-execution experiment

The combined command above prints `42`. Its source program installs nested handlers, forwards an inner `Read` to its outer instance, resumes a deep `once` handler twice at distinct operation sites, and uses simulated resources. The trace verifies clause-local cleanup before tail resumption, exactly one close of the retained handler-frame resource, legal work after resume, and final cleanup of the protected body resource.

`tools/source_syntax.py` reuses the normative lexer's tokens and first checks full EBNF membership. It then constructs a filename/span-bearing AST for the executable subset. Malformed syntax reports `syntax`; valid syntax outside the subset reports `unsupported: Implementation limit`. The legacy `Grammar.lex` token-pair API remains available alongside `lex_spanned`. No grammar productions were changed.

`tools/source_pipeline.py` resolves declarations and fresh binding identities into the existing expression IR. Nonrecursive named functions become checked closures in dependency order, including forward references; every body is checked, even if unused. Closures execute their checked bodies, receiving invocation evidence for ambient calls and retaining lexical evidence for named calls. Source annotations are checked with the existing type matcher and effect-row solver. Written effect rows remain admitted contracts, including when they are wider than the body's inferred effects or occur on returned callable types. Whole-value result-capture bounds remain inferred metadata.

The supported forms are module declarations; explicit fixture imports and aliases; named functions and typed parameters; `Int`/`Unit`, fixture resource and function types; closed effect rows; integer/Unit literals; local bindings, blocks and sequencing; typed-parameter closures and calls (including computed callees); effect families with multiple named operations and `Int`/`Unit` parameters and results; lexical handlers, normal-return clauses, named dispatch, forwarding, `resume`, and `using`. Signed integer literals, decimal/binary/octal/hexadecimal spelling, `int`/`i64` suffixes and the fixed `Int64` range are checked. A semicolon discards an expression under the ordinary usage rules; the final unterminated expression supplies the block result.

The explicit **`eldude::fixture` host profile** supplies simulated `File`/`AsyncFile` ownership tokens, acquisition, consuming close, canonical cleanup, and suspension events. Source must import the names it uses; there is no implicit wildcard prelude or special interpretation of user-defined functions named `acquire` or `close`. The profile's complete contracts and limitations are in [examples/README.md](examples/README.md#fixture-host-profile). The runner calls an exported, nullary `main` returning `Int` or `Unit` as a fixture convention, not a language entry-point rule. Its residual row must have no unhandled algebraic slots; intrinsic `suspend`/`diverge` may be admitted.

`compile_source(text, filename)` and `compile_file(path)` return a `SourceProgram` with `ast`, `expression`, `program`, `inferred`, `functions` and `handled_rows`. With `tools` on Python's import path, pass `checked.program` to `handlers.run` to inspect `Execution.value` and `Execution.events`; `execute_file(path)` combines checking and execution. `Program.origins` maps lowered-node identities to source spans. `Diagnostic` exposes a category, message, primary span and related declaration/transfer spans. CLI failures go to stderr with filename, line and column and exit nonzero before execution.

The source tests exercise accepted traces and static rejections for all three resumption modes, frame transfer, clause-local resources, unsafe abandonment, skipped enclosing obligations, complete deep-resumption residuals and post-resume outward control. Every semantic-rejection fixture is also recognized by the normative grammar. Source integration exposed and corrected a core discrepancy: normal-return clauses had allowed unqualified same-family operation syntax, although [§26.4](docs/language-spec/06-handlers.md#264-same-family-operations-inside-clauses) forbids it inside clauses.

The verified pipeline has **172 passing tests on Python 3.14.8**, including all 91 original IR/grammar regressions, and **133 synchronized grammar productions**. The combined, nested-return, operation-argument and multi-operation CLIs return `42`; the multi-operation affine fixture returns `7`. Syntax, semantic, type and unsupported-feature CLI fixtures exit with status `1` and source-located diagnostics.

This remains a single-file, monomorphic, straight-line experiment. Generic/open-row source contracts, nonempty capture annotations, untyped closure parameters, general operators, branches/loops/recursion, early returns, generic families, non-scalar operation parameters/results or handler results, `self` recursion, top-level value initialization, traits, general imported-code execution, regions and tasks receive implementation-limit diagnostics. Broader inference capabilities remain available in the standalone Python IR tests. Resources are simulated, and suspension/masked cleanup only emit events: there is no scheduler, cancellation delivery, foreign execution or production runtime optimization. The rest of the example corpus retains its staged meanings and expected results; it is not claimed to execute.

The next extension after 0.0.5 supports an enclosing `once`/`affine` operation's `resume` inside a nested handler's normal-return clause, as required by [§25.1](docs/language-spec/06-handlers.md#251-lexical-resumption). Normal completion shares that lexical capability and its ownership state; a nested operation clause introduces its own capability, and a nested function cannot capture either. Resuming transfers the enclosing frame's non-`Dup` captures exactly once while keeping outside obligations live. An inner affine completion that could skip the enclosing resume remains rejected under the prototype's conservative usage rules.

```sh
uv run python tools/run_eldude.py examples/07_source_pipeline/nested_return.eld
# 42
```

This fixture combines deep re-entry with nested normal-return resumption: body cleanup precedes each outer resume, the retained frame closes once, and each returning clause can perform independent work afterward. Static counterexamples cover repeated resume, frame reuse, skipped resumption, outward abandonment and the complete deep residual. No normative grammar or language rules changed.

Effect operations also accept positional `Int`/`Unit` arguments. Their annotated declarations, call arity/types and clause binders are checked. Arguments evaluate once, left to right, before dispatch; their effects and live ownership obligations remain visible. Forwarding passes the evaluated values to the next outer instance. Clause parameters have fresh binding identities and remain distinct from handler-frame captures. Scalar parameters can be used after resumption; resource/callback parameters and destructuring patterns remain outside this slice.

```sh
uv run python tools/run_eldude.py examples/07_source_pipeline/operation_arguments.eld
# 42
```

This fixture sends `7` and `42` through a checked source function, nested forwarding handlers and deep once resumption, while preserving cleanup ordering. Separate tests assert effectful argument evaluation order, callback evidence selection, parameter shadowing, affine abandonment and precise contract diagnostics.

The working-tree multi-operation extension resolves each operation by both family and operation name. Signatures and `tail`/`once`/`affine` modes are checked independently, including unused clauses. Every declared operation needs a clause or explicit `forward operation;`; one `forward ..;` fills only otherwise omitted operations. Duplicate declarations/clauses/forwards and unknown names fail before execution. Empty families have vacuously complete handlers. Unqualified same-family dispatch inside a clause is rejected even when it names another operation; named outer calls remain valid.

```sh
uv run python tools/run_eldude.py examples/07_source_pipeline/multi_operations.eld
# 42
uv run python tools/run_eldude.py examples/07_source_pipeline/multi_operations_deep.eld
# 42
uv run python tools/run_eldude.py examples/07_source_pipeline/multi_operations_affine.eld
# 7
```

The first fixture combines mixed modes, nested instances and selective forwarding. The deep fixture adds one shared linear frame, parameter shadowing, lexical resumption through an empty handler's normal-return clause, an outward sibling-clause effect and independent work after resume. Its frame closes exactly once. The affine variant forwards `stop(7)`, skips the later read, unwinds protected body cleanup and leaves an outside resource available for explicit close.

Effects and evidence still name family instances: two operations on one instance share a slot, while forwarding retains the outer slot. Direct operations use the selected declaration's mode; ordinary calls and complete resumption residuals use the family-level abandonment envelope, including every declared affine operation ([§17.3](docs/language-spec/05-effects-and-failure.md#173-derived-continuation-control-envelope)). Conservative segment/usage checks remain in force even if an admitted operation is not reached in one execution. No grammar, language version, dependency or host-profile change accompanies this extension.

## Inference experiment

`tools/inference.py` checks a small expression IR built with Python tuples. Parameter types and callback usage guarantees are annotated; function result types, effect rows, whole-value result-capture bounds, and closure usage guarantees are inferred from bodies. Calls instantiate those contracts. The experiment reuses the existing row solver unchanged.

Run just the experiment:

```sh
uv run python -m unittest discover -s tools -p 'test_inference.py' -v
```

The cases exercise these outcomes:

| Case | Accepted result | Rejected boundary |
| --- | --- | --- |
| Effectful traversal | An annotated `Int ->{| e} Unit` callback gives traversal the inferred row `{| e}`; a logging callback instantiates it to `{Log}`. Repeated operations reuse one slot. | A callback owning a linear resource cannot satisfy traversal's `Dup + Discard` requirements. |
| Nested same-family handlers | An ambient callback selects the inner `Log`; a lexically named callback retains the outer instance. Removing the inner handler leaves the outer slot. | A closure retaining a named handler cannot escape its delimiter. |
| Scoped state | Reading a local `Ref<Int>` yields `Int`, an empty residual row, and no captures after leaving the region. | Returning the reference or a closure retaining it, or storing an inner closure in an outer cell, fails. |
| Cancellation with ownership | `using` protects a resource across `suspend`; suspending canonical cleanup is checked under its cancellation mask. | An unprotected resource, including a shadowed binding or an argument awaiting later argument evaluation, cannot cross a potentially abandoning call. Masking does not neutralize an affine cleanup effect. |
| Imported `DynArray::freeze` wrapper | The wrapper's contract is inferred, serialized, and loaded into a fresh checker without its body. Instantiating it at `Int` gives a capture-free `List<Int>` that can leave the allocation region. | A list of references to an outer region still retains the inner array's whole bound and cannot leave it. This is the deliberate precision cost of [§13.6](docs/language-spec/04-captures-and-access.md#136-canonical-interfaces-and-conservative-mutation). |

A combined case traverses a list, mutates a local cell, handles logging, and suspends while a resource is protected by `using`. It returns `Int` with only `{suspend}` and no retained captures.

These examples support using one-tail rows and whole-value bounds for this fragment. They also show what the simplification does **not** remove: handler-instance selection, lexical scope checks, ownership tracking, retention horizons, and compatibility checks for callback capture and usage contracts. Callback weakening is allowed at direct argument boundaries; this prototype conservatively requires invariant contracts inside data constructors and callback parameter positions. Nested functions use distinct internal provenance sources before exporting `arg:N`/environment bounds, and ownership is tracked by binding identity across shadowing.

The base inference fragment has straight-line expressions, monomorphic local regions, finite traversal of discardable elements, and tail-handler delimiters. Primitive and imported contracts are trusted inputs; JSON round-tripping demonstrates separate checking, not complete canonical-interface validation. That checker has no Eldude parsing, handler-clause/resumption checking, scheduler, task model, branch/loop inference, trait solving, higher-rank inference, `NonAbandoning` constraint inference, general `mut`-grant checking, or generic retention-horizon solving. Unknown effect tails are treated as potentially abandoning. These experiments do not prove soundness or measure compiler/runtime performance; they leave the language design and existing `.eld` examples unchanged.

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

The counterexamples also check two less visible obligations. A resumed computation admits the **complete handler residual**, including effects introduced by re-entered operation clauses. The checker collects the handled body, normal-return clause and every operation clause into that row, then rechecks every clause with fresh ownership and resumption states. In this straight-line slice, resume adds the supplied residual without selecting new syntax; a stabilization check rejects any row growth after validation. Separately, resources outside the handler remain live after resumption returns; outward control from post-resume code must account for them. Clause-local resources and handler-frame captures have distinct ownership states.

For this fragment, explicit evidence selects the intended instances and single-use continuations can implement the three modes without duplicating resource obligations. The difficult part remains the interaction between residual effects, suspended segments, and ownership. The row solver itself is unchanged.

The experiment supports multiple operations per family, `Int`/`Unit` operation parameters/results and handler results, and straight-line clauses. `Operation(mode, result, parameters=())` declares the positional contract. The annotated IR uses `E('perform_args', family, tuple_of_argument_expressions, *named_instance)` and `E('clause', parameter_names, body)` for parameterized dispatch/clauses; existing nullary `E('perform', family, *named_instance)` and plain clause bodies still work. The executable subset covers literals, bindings, closures/calls, resource acquisition/close, `using`, suspension events, and handlers/resumptions. It conservatively requires non-`Dup` frame captures to remain available until transfer and rejects affine changes needing general usage joins. An opaque `tail`/`once` continuation is treated as non-discardable when a clause attempts outward abandonment. These are prototype restrictions, not new language rules.

`operations=` also accepts named tables such as `{'Read': {'value': Operation('tail', INT, (INT,)), 'tick': Operation('once', UNIT)}}`. `E('perform_op', family, operation_name, argument_tuple, *named_instance)` selects a contract explicitly. `E('handle_ops', family, instance_name, body, named_clause_tuple, returning)` supplies `(operation_name, clause_ir)` entries; each clause uses the existing `clause`/`forward` forms. All clauses and normal return share one logical frame, distinct from each invocation's scalar parameters and clause-local resources. Legacy `{'Read': Operation(...)}` inputs, `perform`, `perform_args` and single-clause `handle` remain supported for singleton families; ambiguous legacy forms are rejected. `Program.operations` contains normalized per-family tables (a legacy unnamed signature uses the `None` key).

Multi-operation dispatch events extend the existing tuple by appending the operation name: `('dispatch', family, instance_name, operation_name)`. Singleton dispatch events retain `('dispatch', family, instance_name)`, and resume/abandon/cleanup event shapes are unchanged. Evaluated argument payloads and operation identity survive every forwarding and continuation wrapper. Direct and generated forwarding dispatch nodes retain source origins.

Resources are simulated ownership tokens; `yield` and masked asynchronous cleanup emit events without scheduling or delivering cancellation. The source frontend above feeds this same experiment. General return/branch/loop elaboration, non-scalar operation parameters, generic families, `self` recursion, task execution, and imported-code execution remain outside it. The interpreter uses recursive Python continuation closures, including for `tail`; it does not demonstrate optimized tail lowering or production runtime performance.
