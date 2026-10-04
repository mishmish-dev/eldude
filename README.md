# Eldude

Eldude is a programming-language design in the pre-implementation stage. This repository contains its design contracts, a grammar recognizer, staged example programs, and an initial standard-library API.

- [Manifesto](design-docs/ELDUDE-MANIFESTO.md): goals and design principles.
- [Language specification](design-docs/ELDUDE-LANGUAGE-SPECIFICATION.md): normative semantics.
- [Formal grammar](design-docs/ELDUDE-FORMAL-GRAMMAR.md): generated presentation of [eldude.ebnf](design-docs/eldude.ebnf), also published as [JSON](design-docs/eldude-grammar.json).
- [Example programs](examples/README.md): incremental `.eld` implementation targets and expected outcomes.
- [Standard-library API](stdlib/README.md) and [profile](design-docs/ELDUDE-STANDARD-LIBRARY.md): initial declarations, ownership contracts, and implementation priorities.
- [Effect-row prototype](tools/effect_rows.py): scoped-row equality and closed-row opening on resolved labels, with [counterexample tests](tools/test_effect_rows.py).
- [Expression inference experiment](tools/inference.py): effectful traversal, nested handlers, scoped state, cancellation checks, and imported capture contracts, with [executable cases](tools/test_inference.py).
- [Handler experiment](tools/handlers.py): clause checking, ownership across resumption, explicit evidence lowering, and a small interpreter, with [accepted programs and counterexamples](tools/test_handlers.py).

The repository's Python tools share a uv project pinned to Python 3.14.8 and use only the standard library. Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then check grammar publications, source syntax, and the prototypes:

```sh
uv sync --locked
uv run python tools/check_grammar.py
uv run python -m unittest discover -s tools -p 'test_*.py'
```

After editing the normative EBNF or the specification excerpts used by the grammar publication, regenerate artifacts with `uv run python tools/check_grammar.py --write`. These checks do not establish type correctness of the `.eld` programs or execute them; there is no Eldude source compiler or production runtime yet.

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

Resources are simulated ownership tokens; `yield` and masked asynchronous cleanup emit events without scheduling or delivering cancellation. There is no source parser, general return/branch/loop elaboration, operation arguments, multi-operation families, `self` recursion, task execution, or imported-code execution. The interpreter uses recursive Python continuation closures, including for `tail`; it does not demonstrate optimized tail lowering or production runtime performance.
