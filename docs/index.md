# Eldude documentation

## Reading guide

- [The Eldude Manifesto](#the-eldude-manifesto): motivation, principles, goals, and scope.
- [Language specification](language-specification.md): twelve chapters, reading paths, and numbered language contracts. Begin with [Foundations and programs](language-spec/01-foundations.md).
- [Formal grammar](formal-grammar.md): source and interface syntax, generated from [eldude.ebnf](eldude.ebnf), with a [JSON export](eldude-grammar.json).
- [Standard-library profile](standard-library.md): collection representations, costs, and ownership contracts, with the initial [API declarations](../stdlib/README.md).
- [Example programs](../examples/README.md): staged programs and expected outcomes.
- [Implementation and development](../README.md): current prototype support, setup, and checks.

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
