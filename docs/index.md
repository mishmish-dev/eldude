# Eldude documentation and project map

<a id="eldude-documentation"></a>

Choose a task below, then read the linked chapter or component. The language specification defines the design; the experimental interpreter implements a subset. A documented rule or library declaration does not by itself imply executable support.

[Reading guide](#reading-guide) · [Language topics](#language-topics) · [Project files](#project-files) · [Editing and checking](#editing-and-checking) · [Manifesto](#the-eldude-manifesto)

## Reading guide

| I need to… | Start here |
| --- | --- |
| Run a program or verify a change | [Quick start and checks](../README.md#quick-start) |
| Format Eldude source or check formatting | [Formatter commands](../README.md#format-source); [design and conventions](formatter.md) |
| Use or extend project tooling | [Project CLI](../README.md#project-cli), [implementation boundaries](implementation.md#project-tooling), and [tooling design](tooling-design.md) with explicit application hosts |
| Understand the design goals | [Manifesto](#the-eldude-manifesto); [precedents](language-spec/precedents.md) for background |
| Look up a language rule | [Topic map below](#language-topics); [specification index](language-specification.md) for conventions and a full reading order |
| Find implemented behavior or a compiler component | [Implementation guide and code/test map](implementation.md) |
| Find capture and existential acceptance coverage | [Positive programs](../examples/README.md#positive-programs), [rejection targets](../examples/README.md#rejection-targets), and [capture contract tests](../tests/source/test_capture_contracts.py) |
| Find a small program or expected diagnostic | [Executable examples](../examples/README.md); [illustrative spec snippets](language-spec/examples.md) |
| Check library APIs, ownership, or cost contracts | [Module/API map](../stdlib/README.md); [library profile](standard-library.md) |
| Work on syntax or grammar consumers | [Normative EBNF](eldude.ebnf); generated [grammar reference](formal-grammar.md) and [JSON export](eldude-grammar.json) |
| Check design scope or review a proposal | [Exclusions and deferrals](language-spec/scope-and-deferrals.md), [invariants checklist](language-spec/invariants.md), [implementation evaluation criteria](language-spec/implementation-criteria.md) |

## Language topics

Use the chapter's local contents and section links for a precise lookup. Chapters 1–10 explain language use; chapters 11–12 are implementer references. Chapter numbers group topics; stable § numbers identify individual contracts.

| Topic / search terms | Chapter | Sections |
| --- | --- | --- |
| Parsing, evaluation order, functions, modules | [1. Foundations](language-spec/01-foundations.md) | §§1–5 |
| Types, generics, records, enums, patterns, `Dup`, `Discard` | [2. Types and ownership](language-spec/02-types-and-ownership.md) | §§6–9 |
| Traits, coherence, associated types, `any` | [3. Traits](language-spec/03-traits.md) | §§10–11 |
| Closures, provenance, retention, `view`, `mut` | [4. Captures and access](language-spec/04-captures-and-access.md) | §§12–15 |
| Effect rows, `diverge`, termination, defects, `Result`, `?`, `try` | [5. Effects and failure](language-spec/05-effects-and-failure.md) | §§16–22 |
| `handle`, `resume`, `tail`, `once`, `affine`, forwarding | [6. Handlers](language-spec/06-handlers.md) | §§23–26 |
| Regions, `Ref`, mutable owners, linear resources, `using` | [7. State and cleanup](language-spec/07-state-and-cleanup.md) | §§27–31 |
| Sequences, indexing, consuming operations, `for`, finite iteration | [8. Collections](language-spec/08-collections.md) | §§32–37 |
| `taskgroup`, `spawn`, `await`, cancellation, inherited handlers | [9. Concurrency](language-spec/09-concurrency.md) | §§38–47 |
| Host contracts, `unsafe`, pointers, native storage, callbacks | [10. Host and FFI](language-spec/10-host-and-ffi.md) | §§48–57 |
| Typing judgments, usage joins, dynamic machine, soundness | [11. Formal semantics](language-spec/11-formal-semantics.md) | §§58–70 |
| Canonical interfaces, ABI, compilation, diagnostics, formatting | [12. Interfaces and tooling](language-spec/12-interfaces-and-tooling.md) | §§71–78 |

## Project files

| Location | Purpose / next stop |
| --- | --- |
| [README.md](../README.md) | Setup, commands, and implementation entry points |
| [AGENTS.md](../AGENTS.md) | Short starting instructions for coding agents |
| [docs/](.) | This map, language contracts, library profile, and grammar publications |
| [src/eldude/](../src/eldude), [tests/](../tests) | Python subpackages (`core`, `source`, `runtime`, `tooling`) and matching test directories; the [implementation file map](implementation.md#file-map) pairs components with tests |
| [examples/](../examples/README.md) | Numbered positive programs and `reject/syntax` / `reject/semantics` counterexamples; [manifest.json](../examples/manifest.json) owns expected positive results and runnable/pending status |
| [stdlib/](../stdlib/README.md) | `.eld` declarations and source bodies, grouped by module; the README maps APIs and implementation status |
| [pyproject.toml](../pyproject.toml), [.python-version](../.python-version), [uv.lock](../uv.lock) | Project metadata, Python version, and locked environment |
| [.gitignore](../.gitignore) | Local environment and Python cache exclusions |
| [Formatter design](formatter.md) | Source formatting guarantees, canonical layout, API, and verification |
| [Tooling design](tooling-design.md) | CLI, projects/workspaces, explicit hosts, compilation, locking, and formatting contract; [implementation guide](implementation.md#project-tooling) records the delivered Python subset |

## Editing and checking

- **Language rules:** edit the owning numbered chapter. The [invariants](language-spec/invariants.md) and example index link to those rules; they do not add competing contracts. Keep existing § identifiers and anchors, and link new references directly to the chapter. The specification index's large [legacy directory](language-specification.md#earlier-section-links) exists only for old bookmarks.
- **Syntax:** edit [eldude.ebnf](eldude.ebnf) and the relevant clauses in [chapter 1](language-spec/01-foundations.md#2-surface-and-parsing-model) or [chapter 12](language-spec/12-interfaces-and-tooling.md#72-canonical-semantic-interfaces). [source/grammar.py](../src/eldude/source/grammar.py) generates `formal-grammar.md` and `eldude-grammar.json`; regenerate with `uv run python -m eldude.source.grammar --write` instead of editing outputs.
- **Implementation:** check the [supported subset and limits](implementation.md#source-to-execution-experiment), then use the [code/test map and package boundaries](implementation.md#file-map). The public source API, elaboration/checking, and runtime execution have separate modules and focused test suites. Grammar acceptance, static checking, and execution are separate checks.
- **Library and examples:** keep the [library profile](standard-library.md), declarations, and example expectations consistent. Preserve expected results independently of the implementation. Spec snippets may be schematic or deliberately rejected; executable expectations belong in the example corpus.
- **Verification:** use the [root README commands](../README.md#checks). [tooling/check_docs.py](../src/eldude/tooling/check_docs.py) checks local links and fragment anchors, chapter/code map coverage, and documented example results. It checks the inline links and heading/HTML anchors used here; it skips code examples and external URLs. When moving prose, update incoming links and keep useful anchors. Update this map when an entry point or file responsibility changes.

For a narrow lookup, search the owning file: `rg -n '^#{2,3} ' docs/language-spec/06-handlers.md` lists its sections; `rg -n 'resume' src/eldude/core/handlers.py tests/core/test_handlers.py` finds the matching implementation and checks.

## The Eldude Manifesto

Eldude is a high-level, strict, statically typed functional programming language. It aims to make demanding programs understandable.

It draws on Rust's ownership and traits, Koka's effects and handlers, and ML/OCaml's strict evaluation and modules. Other influences include Haskell's purity and type classes, Clean and Linear Haskell's usage rules, and Roc's separation of applications from their host platform.

### Motivation

Much of programming's difficulty lives between features. A file is easy to close until a request is cancelled. A callback is easy to pass until it outlives its state.

Eldude seeks a small set of mechanisms that remain understandable together. We value local reasoning, visible obligations, predictable behavior, and practical restraint.

### Principles

**Reason locally.** Understanding a function should require its source and the public contracts of its dependencies. Module boundaries must support independent checking, including for generic code.

**Make behavior visible.** Immutable values and strict evaluation are the foundation. Effects, mutation, suspension, and possible nontermination belong in explicit contracts. Expected failure is data, represented by `Result`.

**Keep distinct concerns distinct.** Effects describe behavior; ownership describes responsibility; regions bound mutable state. Each mechanism needs a clear job and clear rules for composing with the others.

**Preserve obligations through abstraction.** Collections, closures, handlers, and tasks obey the same ownership rules. Putting a file in a list must not make closing it optional.

**Give work and resources a scope.** Cleanup and child-task lifetimes have explicit owners. Returning early, cancelling, or handling an effect must respect the responsibilities crossed along the way.

**Make complexity earn its place.** One concept should have one primary mechanism; semantic information should be written once. Every feature must justify its cost to programmers and compilers, including its interactions with the rest of the language. Conservative checking is acceptable when it keeps the language predictable.

**Treat tooling as language design.** Parsing must stand on syntax alone. Public contracts must be readable. Diagnostics should explain which obligation was violated and where it came from.

**Keep concurrency structured and cooperative.** Code that starts concurrent work remains responsible for waiting for it and its cleanup to finish, including during cancellation. Tasks take turns at explicit waiting or yielding points, and ordinary functions declare whether they may yield.

**Make foreign contracts explicit.** Foreign function interface bindings must describe ownership, memory lifetime, callbacks, and effects. Safe wrappers expose audited native contracts through ordinary APIs. Programmers must explicitly take responsibility for safety conditions the compiler cannot check; other language checks remain in force.

### Goals

- Make pure, non-diverging functions the default, with explicit contracts for code that needs more.
- Make state, resources, effects, and concurrency safe to use together through ordinary abstractions.
- Support efficient implementations and native integration through narrow, explicit trust boundaries.
- Keep separate compilation, incremental checking, and dependable tooling central to the design.

### Non-goals

Eldude does not aim to maximize expressiveness or provide a feature for every convenience. The current design excludes general references and lifetime syntax, implicit effectful destruction, detached tasks, and unrestricted type-level computation.

User-directed shared-memory parallelism is outside the current scope. Many-shot continuations are deferred until concrete programs justify their cost.

A deferred feature needs evidence before admission. An explicit scope boundary needs a deliberate decision to expand the language.

Detailed rules belong in the [language specification](language-specification.md); syntax belongs in the [formal grammar](formal-grammar.md).

## The name

Eldude is named after the El Dude Brothers (Mark Corrigan and Jeremy Usbourne).
