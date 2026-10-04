# Eldude

Eldude is a programming-language design with an experimental implementation. This repository contains its design contracts, a grammar recognizer, a bounded source-to-execution pipeline, staged example programs, and an initial standard-library API.

Release **0.0.5** adds the first source-to-execution pipeline, implementing a subset of the unchanged Eldude **0.0.4** language contract.

- [Manifesto](design-docs/ELDUDE-MANIFESTO.md): goals and design principles.
- [Language specification](design-docs/ELDUDE-LANGUAGE-SPECIFICATION.md): normative semantics.
- [Formal grammar](design-docs/ELDUDE-FORMAL-GRAMMAR.md): generated presentation of [eldude.ebnf](design-docs/eldude.ebnf), also published as [JSON](design-docs/eldude-grammar.json).
- [Example programs](examples/README.md): incremental `.eld` implementation targets and expected outcomes.
- [Standard-library API](stdlib/README.md) and [profile](design-docs/ELDUDE-STANDARD-LIBRARY.md): initial declarations, ownership contracts, and implementation priorities.
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

After editing the normative EBNF or the specification excerpts used by the grammar publication, regenerate artifacts with `uv run python tools/check_grammar.py --write`. Grammar acceptance alone does not establish type correctness or execute a program. The source runner checks and executes the subset below; this is not a production compiler or runtime.

## Source-to-execution experiment

The combined command above prints `42`. Its source program installs nested handlers, forwards an inner `Read` to its outer instance, resumes a deep `once` handler twice at distinct operation sites, and uses simulated resources. The trace verifies clause-local cleanup before tail resumption, exactly one close of the retained handler-frame resource, legal work after resume, and final cleanup of the protected body resource.

`tools/source_syntax.py` reuses the normative lexer's tokens and first checks full EBNF membership. It then constructs a filename/span-bearing AST for the executable subset. Malformed syntax reports `syntax`; valid syntax outside the subset reports `unsupported: Implementation limit`. The legacy `Grammar.lex` token-pair API remains available alongside `lex_spanned`. No grammar productions were changed.

`tools/source_pipeline.py` resolves declarations and fresh binding identities into the existing expression IR. Nonrecursive named functions become checked closures in dependency order, including forward references; every body is checked, even if unused. Closures execute their checked bodies, receiving invocation evidence for ambient calls and retaining lexical evidence for named calls. Source annotations are checked with the existing type matcher and effect-row solver. Written effect rows remain admitted contracts, including when they are wider than the body's inferred effects or occur on returned callable types. Whole-value result-capture bounds remain inferred metadata.

The supported forms are module declarations; explicit fixture imports and aliases; named functions and typed parameters; `Int`/`Unit`, fixture resource and function types; closed effect rows; integer/Unit literals; local bindings, blocks and sequencing; typed-parameter closures and calls (including computed callees); single-operation nullary effect families; lexical handlers, normal-return clauses, named dispatch, forwarding, `resume`, and `using`. Signed integer literals, decimal/binary/octal/hexadecimal spelling, `int`/`i64` suffixes and the fixed `Int64` range are checked. A semicolon discards an expression under the ordinary usage rules; the final unterminated expression supplies the block result.

The explicit **`eldude::fixture` host profile** supplies simulated `File`/`AsyncFile` ownership tokens, acquisition, consuming close, canonical cleanup, and suspension events. Source must import the names it uses; there is no implicit wildcard prelude or special interpretation of user-defined functions named `acquire` or `close`. The profile's complete contracts and limitations are in [examples/README.md](examples/README.md#fixture-host-profile). The runner calls an exported, nullary `main` returning `Int` or `Unit` as a fixture convention, not a language entry-point rule. Its residual row must have no unhandled algebraic slots; intrinsic `suspend`/`diverge` may be admitted.

`compile_source(text, filename)` and `compile_file(path)` return a `SourceProgram` with `ast`, `expression`, `program`, `inferred`, `functions` and `handled_rows`. With `tools` on Python's import path, pass `checked.program` to `handlers.run` to inspect `Execution.value` and `Execution.events`; `execute_file(path)` combines checking and execution. `Program.origins` maps lowered-node identities to source spans. `Diagnostic` exposes a category, message, primary span and related declaration/transfer spans. CLI failures go to stderr with filename, line and column and exit nonzero before execution.

The source tests exercise accepted traces and static rejections for all three resumption modes, frame transfer, clause-local resources, unsafe abandonment, skipped enclosing obligations, complete deep-resumption residuals and post-resume outward control. Every semantic-rejection fixture is also recognized by the normative grammar. Source integration exposed and corrected a core discrepancy: normal-return clauses had allowed unqualified same-family operation syntax, although §26.4 forbids it inside clauses.

The verified milestone has **132 passing tests on Python 3.14.8**, including all 91 prior regressions, and **133 synchronized grammar productions**. The combined CLI returns `42`; syntax, semantic and unsupported-feature CLI fixtures exit with status `1` and source-located diagnostics.

This remains a single-file, monomorphic, straight-line experiment. Generic/open-row source contracts, nonempty capture annotations, untyped closure parameters, general operators, branches/loops/recursion, early returns, multi-operation/generic families, operation arguments, non-scalar handler results, `self` recursion, top-level value initialization, traits, general imported-code execution, regions and tasks receive implementation-limit diagnostics. Broader inference capabilities remain available in the standalone Python IR tests. Resources are simulated, and suspension/masked cleanup only emit events: there is no scheduler, cancellation delivery, foreign execution or production runtime optimization. The rest of the example corpus retains its staged meanings and expected results; it is not claimed to execute.

One inherited handler boundary is now explicit: an enclosing operation clause's resumption cannot currently be invoked from a nested handler's normal-return clause. This valid lexical use under §25.1 reports an implementation limit; supporting it requires threading the capability and its ownership state through normal completion.

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
| Imported `DynArray::freeze` wrapper | The wrapper's contract is inferred, serialized, and loaded into a fresh checker without its body. Instantiating it at `Int` gives a capture-free `List<Int>` that can leave the allocation region. | A list of references to an outer region still retains the inner array's whole bound and cannot leave it. This is the deliberate precision cost of §13.6. |

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

The counterexamples also check two less visible obligations. A resumed computation admits the **complete handler residual**, including effects introduced by re-entered operation clauses. The checker first infers that row and then rechecks the clause with it at resume sites. Separately, resources outside the handler remain live after resumption returns; outward control from post-resume code must account for them. Clause-local resources and handler-frame captures have distinct ownership states.

For this fragment, explicit evidence selects the intended instances and single-use continuations can implement the three modes without duplicating resource obligations. The difficult part remains the interaction between residual effects, suspended segments, and ownership. The row solver itself is unchanged.

The experiment has one nullary operation per family, `Int`/`Unit` operation and handler results, and straight-line clauses. The executable subset covers literals, bindings, closures/calls, resource acquisition/close, `using`, suspension events, and handlers/resumptions. It conservatively requires non-`Dup` frame captures to remain available until transfer and rejects affine changes needing general usage joins. An opaque `tail`/`once` continuation is treated as non-discardable when a clause attempts outward abandonment. These are prototype restrictions, not new language rules.

Resources are simulated ownership tokens; `yield` and masked asynchronous cleanup emit events without scheduling or delivering cancellation. The source frontend above feeds this same experiment. General return/branch/loop elaboration, operation arguments, multi-operation families, `self` recursion, task execution, and imported-code execution remain outside it. The interpreter uses recursive Python continuation closures, including for `tail`; it does not demonstrate optimized tail lowering or production runtime performance.
