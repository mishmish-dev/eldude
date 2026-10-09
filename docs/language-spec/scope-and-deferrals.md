# Appendix A — Deliberately Absent or Deferred Features

[Specification index](../language-specification.md)

This reference is normative with respect to the current design scope. It applies the distinction in the [manifesto](../index.md#the-eldude-manifesto): a deferred feature needs concrete evidence before admission; an explicit scope exclusion needs a deliberate decision to expand the language. Neither category is an implementation backlog or a promise of eventual inclusion.

An extension must justify its interactions with ownership, effects, regions, control flow, separate compilation, and tooling. A library proposal remains within the existing language contracts unless a scope change is explicitly adopted.

## A.1 General reference/lifetime machinery

The current design excludes:

- general safe `&T` / `&mut T` references;
- source lifetime parameters/outlives constraints;
- inferred callable lifetime preconditions or a general outlives solver;
- general borrow expressions;
- first-class borrowed slices into mutable owners;
- Rust-style borrow inference.

Temporary access uses `view`/`mut`; retained mutable identity uses region-indexed nominal abstractions; interior inspection uses scoped projection.

Aliasable cells require the ordinary intrinsic payload bound `CaptureFree + Discard` ([§13.5](04-captures-and-access.md#135-retention-horizons)); `CaptureFree` describes every value of a type, independently of scope ordering. Mutable storage with scoped contents uses exclusive ownership and conservative whole-owner capture accounting. Existing lexical validity and non-escape checks remain part of the language.

## A.2 Concurrency/parallelism machinery

The current design excludes:

- `async fn`;
- a language `Future` layer;
- detached tasks as a core primitive;
- source-level shared-memory parallel execution;
- `Send`, `Sync`, `Transfer`, or equivalent ordinary type predicates;
- implicit task migration semantics based on captured value types;
- a public general task-handle `select` primitive.

Structured cooperative concurrency remains fully specified.


## A.3 Pinning and physical identity

The current design excludes:

- `Pin`/`Pinned`/`Unpin`;
- immovable ordinary types;
- stable physical addresses as an ordinary value property;
- safe general self-referential value construction.

Foreign stable identity/storage uses explicit FFI abstractions.

<a id="a4-type-system-surface-deferred"></a>

## A.4 Type-system exclusions and deferrals

The current scope excludes unrestricted type-level computation, including:

- unrestricted type-level general recursion;
- arbitrary theorem proving during ordinary checking.

The bounded static rules in [§§7.3](02-types-and-ownership.md#73-compile-time-naturals) and [10.6](03-traits.md#106-implicit-implementation-patterns-and-selection)–[10.8](03-traits.md#108-associated-equations-and-normalization) are the current contract. Replacing them with unrestricted computation requires a deliberate scope decision.

The following surface extensions are deferred pending concrete programs and a composition design:

- structural records;
- structural variants;
- `some Trait`;
- general explicit existential syntax;
- surface type-level lambdas;
- refinement-type syntax;
- units-of-measure syntax;
- session/protocol syntax;
- symbolic termination measures and `decreases` annotations.

GADTs, nominal opacity, associated types, GATs, higher-rank/higher-kinded polymorphism, and compile-time naturals provide the current abstraction surface.

## A.5 Syntax conveniences deferred

The following syntax forms are absent from the current language. Proposals for conveniences require evidence that ordinary functions and types are insufficient. A proposal that also changes an explicit architectural boundary, such as fixed operator parsing in [§2.3](01-foundations.md#23-operators), additionally requires a scope decision:

- implicit currying;
- partial-application syntax;
- labelled/default parameters;
- named call arguments;
- pipeline syntax;
- range-expression syntax;
- dedicated slicing syntax;
- map/set literal syntax;
- generic attribute syntax;
- string interpolation;
- raw/multiline string syntax;
- handler-list syntax;
- special cancellation statements;
- conversion operator `as`;
- dedicated core test/expect syntax;
- user-defined operator precedence.

Ordinary functions/types may provide equivalent library ergonomics when appropriate.

## A.6 Runtime/language mechanisms deliberately excluded

- local reassignment;
- null;
- unchecked implicit exceptions;
- structural `error { ... }` set types;
- general-purpose `panic`;
- implicit effectful destruction;
- surface `unique` qualifiers;
- capability types as a parallel permission system;
- overlapping/incoherent implicit traits;
- mandatory whole-program monomorphization;
- ambient executable module initialization;
- first-class handler values/types;
- source-level host-selection declarations.

## A.7 Open standard-library design areas

The following are intentionally not fixed by the core architecture and may evolve without changing the fundamental semantic model:

- exact `DiagnosticRecord` field schema;
- exact names and breadth of standard host effects (`fs`, `net`, `clock`, etc.);
- exact collection representations/cost models beyond the bundled standard-library profile;
- exact owning immutable subview types;
- decimal numeric model;
- high-level stream/source abstractions;
- exact names/breadth of ownership-preserving projection and traversal combinators satisfying [§§15](04-captures-and-access.md#15-scoped-access-projection) and [35](08-collections.md#35-iteration);
- exact names/breadth of structured-concurrency combinators satisfying [§46.6](09-concurrency.md#466-standard-structured-concurrency-combinators);
- specialized native arenas/supervision libraries.

Parallel computation remains subject to [§38.3](09-concurrency.md#383-parallelism). A library may use existing audited host/native facilities within those contracts. Adding user-directed shared-memory execution of ordinary Eldude strands would expand the language scope and requires a deliberate design decision as well as evidence from concrete workloads; it is not an ordinary library-policy change.

## A.8 Deferred or removed algebraic-control variants

The core has no separate `abort` resumption mode. Abortive operations use `affine ... -> Never`, so continuation abandonment follows the ordinary affine rule.

Many-shot algebraic resumption is deferred. Reintroducing it would require a demonstrated need for continuation duplication plus a separately reviewed composition story for usage, mutable state, handlers, concurrency, and separate compilation. It is not accepted merely as the completion of a resumption-mode feature matrix.
