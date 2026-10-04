# Appendix C — Architectural Precedents

[Specification index](../language-specification.md)

This appendix is non-normative. Eldude combines established ideas rather than treating them as inventions.

- **ML / OCaml:** strict functional evaluation, nominal algebraic data, module abstraction, separate compilation, and a clear distinction between concurrency and parallelism in modern runtimes.
- **Haskell:** purity, higher-order functional design, type classes, rank polymorphism, local-state encapsulation, stable foreign handles, structured resource combinators, and pure-parallelism precedent.
- **Koka / algebraic-effects research:** row-polymorphic effects, handlers, explicit divergence, state-heap encapsulation, and handler-oriented asynchronous control.
- **Rust:** explicit resource ownership, associated types, coherent-ish trait discipline, `Result` ergonomics, unsafe proof boundaries, and the cautionary complexity of general borrowing, `Send`/`Sync`, and pinning.
- **Clean / Linear Haskell / linear logic:** usage-sensitive ownership and destructive-update opportunities derived from uniqueness/linearity rather than exposed storage mutation.
- **Roc:** host/platform separation and value-oriented runtime freedom.
- **Capture-checking research:** explicit tracking of retained obligations separately from invocation effects.
- **Structured-concurrency/nursery designs:** lexical ownership and cancellation of child work.
- **Region calculi and `ST`-style local state:** generative state identity that cannot escape its lexical boundary.

The normative semantics of Eldude are defined by this specification, not by any precedent.
