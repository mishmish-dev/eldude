# The Eldude Manifesto

**Version:** 0.0.1  
**Status:** architectural consolidation; pre-implementation

Eldude is a strict, statically typed, non-diverging-by-default functional language for application, systems, and library programming. Possible nontermination must be admitted explicitly as `diverge`; absence of `diverge` does not mean that every well-typed computation is guaranteed to produce a normal result rather than terminate at an explicit nonrecoverable defect boundary. Its design objective is not maximal expressiveness per mechanism. It is a small set of orthogonal semantic mechanisms that remain understandable when composed.

Eldude treats compiler complexity, hidden runtime behavior, and cross-feature interaction as language-design costs. A feature is justified only when it provides a capability that cannot be expressed cleanly by mechanisms already present.

The core semantic model is:

```text
values       data and ownership
effects      behavior represented in effect rows
captures     retained obligations and provenance
regions      lifetime of mutable identity
usage        duplication, discard, and exact consumption
handlers     interpretation of algebraic operations
taskgroups   structured concurrent lifetime
host         external runtime boundary
unsafe       explicit unverified proof boundary
```

These dimensions are deliberately distinct. Effects do not encode ownership. Captures do not encode invocation behavior. Regions do not imply allocators. Usage does not imply physical uniqueness. The host is not an ambient capability object. `unsafe` is not an effect. Recoverable or continuing structural exits such as cancellation and affine zero-resumption control are not a separate semantic dimension; their legality is determined by the ordinary obligations they cross. Nonrecoverable defects are different: they terminate the current Eldude execution rather than transfer control to a recoverable Eldude continuation.

---

# I. Design laws

## 1. One semantic concept should have one primary mechanism

Eldude avoids parallel feature families that solve the same problem with slightly different rules.

Examples:

- one function type syntax: `fn(A, B) -> C`;
- one function/lambda introducer: `fn`;
- one algebraic handler construction form: `handler`;
- one explicit cleanup boundary: `using`;
- one structured concurrency boundary: `taskgroup`;
- one expected-failure representation: `Result`;
- one dynamic trait-erasure form: `any Trait`.

Eldude therefore does not add currying, partial application, `async fn`, handler lists, implicit destructors, general borrow syntax, or a second exception mechanism merely for convenience.

This law governs the language's primary abstractions and conventions; it is not a claim that a sufficiently general mechanism cannot encode behavior resembling another mechanism. In particular, `Result` is the standard representation for routine expected failure even though affine zero-resumption algebraic control can express other dynamically handled control protocols.

## 2. Semantic information should appear once

Eldude rejects redundant annotations when another part of the type already establishes the fact.

An effect-row variable is declared as `!e`, but inside an effect row it is simply `e`:

```eldude
fn apply<A, B, !e>(
    f: fn(A) ->{e} B,
    value: A,
) ->{e} B;
```

A structure containing a linear field is linear without repeating `linear` on the structure. A handler application does not repeat its effect family when the handler type already determines it.

This law concerns source-level semantic redundancy. Canonical interfaces may restate a fact derived from hidden representation when clients must know that fact without inspecting the representation; such a summary is a contract boundary, not a second source of truth.

## 3. Parsing is independent of semantic analysis

Eldude source can be parsed without name resolution, type checking, imported implementation bodies, or trait resolution.

The language uses:

- braces and semicolons;
- a fixed, normative token/operator inventory and precedence table;
- `::` for qualification;
- angle brackets for type arguments;
- turbofish for explicit expression type application;
- explicit imports without wildcard imports.

The Full Specification publishes the normative surface grammar needed to enforce this law. In particular, `!` is reserved for effect-category syntax (`!e` at effect-row generic declaration sites and `!Effect::op(...)` for algebraic operation dispatch), not overloaded as a general expression-prefix operator. Expression-level type application uses turbofish specifically so `<...>` never requires name resolution to distinguish a comparison from generic application.

User-defined operators and precedence are excluded. Many-shot resumption is deferred and `many` is not reserved as a keyword in the 0.0.1 source grammar.

## 4. Local reasoning is a design requirement

Understanding a function should not require reconstructing a whole-program alias graph, scheduler state, import-dependent instance search, or hidden destruction behavior. Local reasoning may depend on the function's own source and the canonical semantic interfaces of its direct dependencies; it must not require imported implementation bodies.

Eldude therefore prefers:

- call-scoped `view` and `mut` over general references;
- generative lexical regions over lifetime inequalities;
- coherent traits over overlapping instance search;
- explicit `using` over implicit effectful destruction;
- structured task scopes over detached tasks;
- canonical module interfaces over implementation inspection.

**Common structural-exit law.** Every non-local exit that continues Eldude execution elsewhere is checked by the same obligation-discharge rule. This includes `return`, `?`, loop exits crossing a scope, affine zero-resumption control, and cooperative cancellation. An exit is legal only when each crossed obligation is already discharged, is transferred to the exit target, is discardable, or is owned by a structural frame such as `using` or `taskgroup` whose exit semantics discharge it. Feature-specific control mechanisms do not get independent escape rules. Every reachable ordinary suspension point must also be legal as a possible cancellation exit under this rule unless execution is inside explicitly cancellation-masked structural discharge such as `Cleanup` execution or taskgroup shutdown. Assertion defects are not checked as recoverable exits: structural owners still perform their specified best-effort unwinding, but naked linear obligations are not required to be discharged on a path that terminates at the nonrecoverable defect boundary.

## 5. Compiler complexity is paid by every program

A feature that requires whole-program reasoning, unstable inference, global alias analysis, or implementation-dependent typing is expensive even when its syntax is small.

Eldude accepts conservative checking where exact inference would make the language substantially less predictable. When termination or control safety cannot be proved, the program admits `diverge` or is rejected at the relevant safety boundary rather than relying on undocumented heuristics.

The same burden applies to mechanisms already present in the design. High-cost features are not exempt merely because they appear in an early draft: they must justify their cross-feature checking, diagnostics, runtime, and separate-compilation costs with concrete programs. The 0.0.1 core therefore defers many-shot resumption rather than forcing arbitrary continuation duplication through usage, handlers, concurrency, state, and separate compilation before a concrete need earns that cost.

## 6. Defer generality until a concrete use case earns it

Eldude intentionally omits mechanisms whose main justification is future flexibility.

Notably, the current design has no:

- general safe reference type;
- lifetime language;
- `Send`/`Sync`/`Transfer` axis;
- pinning/immovable-value system;
- explicit shared-memory parallelism model;
- general-purpose capability system;
- unrestricted type-level computation.

The absence is deliberate. A mechanism may be deferred because no concrete program has yet earned its complexity, or because the current language version deliberately excludes a known capability from scope. Those are different claims and should be recorded separately. A deferred mechanism may be reconsidered when concrete programs cannot be expressed cleanly by the existing model or when a scoped-out capability becomes a release requirement.

---

# II. Ordinary values and functions

## 7. Ordinary data has value semantics

Eldude programs reason about values, not storage locations.

```eldude
let a = value;
let b = a;
```

is permitted exactly when the value is semantically duplicable. Representation sharing, copy-on-write, destructive reuse of dead storage, stack allocation, reference counting, or tracing collection are implementation choices unless the program explicitly uses mutable identity or foreign memory.

Physical address is never part of ordinary safe value semantics.

## 8. Bindings do not change

`let` bindings are immutable. Same-scope shadowing creates a new binding:

```eldude
let x = 1;
let x = x + 1;
```

There is no assignment expression, assignment statement, compound assignment, or `let mut`.

Mutable identity exists only through explicit state abstractions.

Local inferred polymorphism is deliberately conservative around effects and identity. A `let` binding is implicitly generalized only when evaluating its initializer has no admitted effect and the generalized variables are not already fixed by the surrounding type, capture/provenance, region, usage, access, or structural context. Lexical region identities are never implicitly generalized. In particular, constructing mutable identity such as `Ref<T,@r>` performs `state<@r>` and therefore cannot create a polymorphic mutable cell by local generalization. When these conditions do not hold, the binding remains monomorphic.

## 9. Evaluation is strict and left-to-right

Eldude is call-by-value. Functions and arguments are evaluated left-to-right. Optimization may change representation and scheduling only when observable semantics are preserved.

This includes preservation of:

- effect order;
- defect order;
- divergence behavior;
- handler behavior;
- resource obligations;
- explicit suspension/interleaving semantics.

## 10. Functions have fixed arity and one arrow

```eldude
fn(A) -> B
fn(A, B) -> C
fn(A) ->{fs} B
```

There is no unary-arrow shorthand and no implicit currying.

Partial application is expressed by an ordinary closure:

```eldude
let addTwo = fn(x: Int) => add(2, x);
```

Parameters are positional. Labelled parameters and default arguments are not core language features.

## 11. Closure multiplicity follows captured obligations

Eldude does not have separate `Fn`, `FnMut`, and `FnOnce` families.

Closures capture owned values. `view` and `mut` access cannot be captured.

A closure whose retained environment is duplicable and discardable is unrestricted. A closure retaining an affine obligation is affine. A closure retaining a linear obligation is linear.

Calling a function value consumes one logical instance of that value. An unrestricted function value may therefore be called repeatedly; a linear closure may be called exactly once.

This same rule applies to other first-class callable packages. Lexical handler frames are not first-class values in the 0.0.1 core. Callable-environment captures and result provenance are distinct contracts: every callable also has a compiler-tracked result-capture relationship describing which argument or environment provenance may be retained by its result. Public and erased callables preserve that relationship through canonical interfaces; abstraction cannot turn a region-, taskgroup-, effect-instance-, or foreign-tied result into provenance-free data.

---

# III. Types, abstraction, and usage

## 12. Nominal algebraic data is primary

Eldude uses nominal `struct` and `enum` types, exhaustive pattern matching, GADTs, higher-rank polymorphism where explicit, higher-kinded parameters, and compile-time natural parameters.

Structural records, general explicit existentials, and type-level lambdas are not currently part of the language.

## 13. Usage has two primitive permissions

The compiler recognizes two intrinsic predicates:

```text
Dup       the value may be semantically duplicated
Discard   the value may be abandoned without consuming it
```

They induce the familiar usage classes:

```text
                Dup   Discard
unrestricted    yes   yes
affine           no   yes
linear           no    no
```

`Dup` and `Discard` use trait-like constraint syntax but are not user-implementable traits. Primitive and intrinsic types have compiler-defined permissions; composite types derive the maximum permissions justified by their contents. A nominal declaration may deliberately strengthen its usage obligation by withholding a permission even when its representation would permit it, for example `linear struct File;` or `affine struct CancelToken;`. A declaration may never weaken an obligation implied by its fields or other contained obligations.

This is preferable to proliferating special modes. The same permissions govern collections, closures, task handles, erased values, and generic algorithms. Nominal strengthening creates resource roots without creating another ownership axis.

## 14. Traits are coherent

Trait resolution terminates and is independent of import order. An implicit implementation belongs to the module that defines either the trait or the nominal implementing type.

Overlapping or incoherent implicit implementations are excluded. Alternative behavior uses explicit wrapper values or dictionaries.

Associated types and generic associated types are supported when checking remains decidable.

## 15. Static opacity uses nominal types; dynamic erasure uses `any`

Eldude has no `some Trait` construct.

Static implementation hiding uses ordinary nominal abstraction: a module exports a nominal type while hiding its representation.

Runtime heterogeneity uses:

```eldude
any Trait
```

Dynamic compatibility is deliberately conservative and closed. An `any Trait<...>` package is formable only when the package interface satisfies Eldude's `DynCompatible` judgment using canonical interface information alone. In the 0.0.1 core every trait method belongs to that dynamic interface: it must have a receiver, declare no method-local generic parameters, expose no concrete `Self` outside the receiver, use no GAT projection, and resolve every associated type used by the callable signature to a package-visible type. Any remaining method constraint, effect contract, or result-capture relationship must be expressible from the erased package interface without knowing the hidden concrete implementation type.

Because there is no per-method dynamic-exclusion syntax, one incompatible method makes that `any Trait<...>` form invalid. Static-only behavior remains available through nominal abstraction, explicit wrappers/dictionaries, or a separate dyn-compatible trait. Dynamic compatibility is therefore a deterministic interface property, not an implementation-body heuristic.

Erasure hides representation, not obligations. A bare `any Trait` promises no `Dup` or `Discard` property and is therefore used conservatively. Stronger packages state guarantees explicitly:

```eldude
any Source + Discard
any Source + Dup + Discard
```

A bare `any Trait` is therefore an ownership-bearing erased package, not the default choice for heterogeneous values that may simply be abandoned. General-purpose erased containers and return values should request `+ Discard` when abandonment is part of their contract. A public API that returns a non-`Discard` erased package should expose an obvious consuming or discharge path; tooling may warn when an exported erased obligation appears unusable. This is an ergonomic discipline, not a new soundness predicate.

Captures and region provenance remain statically visible through erasure. Dynamic dispatch does not weaken any ordinary usage, capture, region, effect, mutable-owner, or result-provenance obligation.

---

# IV. Effects, non-divergence, handlers, and failure

## 16. Pure and non-diverging is the shortest contract

```eldude
fn(A) -> B
```

means no admitted ordinary effect and no admitted nontermination, subject to the contracts of primitives, foreign functions, handlers, and the host. It does not promise defect-freedom: an explicit failed assertion may terminate the computation at the host diagnostic boundary instead of producing `B`.

Possible nontermination is represented by the intrinsic semantic effect:

```eldude
diverge
```

There is no separate partial-function arrow.

When the compiler cannot prove absence of nontermination, it admits `diverge` rather than pretending the computation is non-diverging. This is the sense in which Eldude is non-diverging-by-default.

## 17. Effects describe admitted computation behavior

Effects are visible in function types. They describe the behaviors represented in Eldude effect rows; they are not an exhaustive catalogue of every observable structural outcome of evaluation.

```eldude
fn(Path) ->{fs} Bytes
fn() ->{net, suspend, diverge} Response
```

Eldude distinguishes:

- algebraic effect families, which may be interpreted by handlers;
- intrinsic semantic effects such as `diverge` and `suspend`;
- region state effects `state<@r>`.

`suspend`, `diverge`, and `state<@r>` are not ordinary user-handleable algebraic operations. Defect termination and cooperative cancellation are not effect-row entries; they are structural control outcomes governed by their dedicated rules.

Effect rows also determine a compiler-derived **continuation-control envelope**. In the 0.0.1 core, the relevant property is whether evaluation may abandon the surrounding continuation. The envelope is evaluated relative to the current structural-control context: `suspend` contributes an abandonment path only when cooperative cancellation is unmasked at that point, while an algebraic family with an `affine` operation contributes an abandonment path regardless of cancellation masking unless that family is handled before the boundary. `tail` and `once` operations are non-abandoning. In ordinary unmasked code, an unconstrained open effect-row variable is checked conservatively as potentially abandoning. This envelope is derived from existing effect declarations and structural masks; it is not a new source-level effect or permission axis.

Eldude 0.0.1 exposes one compiler-governed constraint on that already-derived property:

```eldude
where e: NonAbandoning
```

`NonAbandoning` is intrinsic to effect rows. It is not a trait, capability, or effect family and cannot be implemented by users. It describes the ordinary **unmasked** row contract and permits generic code to quantify over unknown ordinary effects while promising that those effects cannot abandon the caller's continuation. Structural masks may make a particular execution context less abandoning than the unmasked row without changing the row's `NonAbandoning` status.

At an ordinary call or other opaque effectful boundary, the checker applies the envelope to the live continuation. A potentially abandoning computation is legal only when the continuation that could be abandoned satisfies the common structural-exit law. Handling an algebraic family locally removes that family's contribution from the residual row. This is what makes effect control behavior compose through higher-order functions and separate compilation.

## 18. `suspend` is the concurrency-visible effect

`suspend` means that the current strand may reach a point where execution yields its domain and another strand may run.

Actual suspension points include operations such as `await`, `task::yield()`, and host operations whose contract permits suspension.

A row containing `suspend` is an upper bound: merely calling a function whose type admits `suspend` does not itself deliver cancellation. When execution actually reaches an ordinary suspension point, however, pending cancellation may be delivered there unless execution is inside cancellation-masked structural discharge. Because `suspend` is therefore potentially continuation-abandoning, effect-polymorphic code retaining non-`Discard` obligations across an unconstrained effectful call is rejected unless those obligations have a structural discharge path. Eldude does not add a second `cancellable` versus `noncancellable` suspension property.

## 19. Algebraic control is explicit

User-defined effects declare the resumption behavior of every operation:

```text
tail     resume exactly once as final semantic action
once     resume exactly once
affine   resume zero or one time
```

Handlers are deep. Resumption is lexical and written only as:

```eldude
resume(value)
```

There is no first-class continuation variable. Many-shot resumption is not part of the 0.0.1 core; it is deferred until concrete programs and implementation evidence justify continuation duplication.

Eldude has no separate `abort` resumption mode. An operation that is semantically abortive is written as an `affine` operation returning `Never`:

```eldude
effect Raise<E> {
    affine raise(error: E) -> Never;
}
```

Safe code cannot manufacture a `Never` value with which to resume, so a terminating handler path for such an operation necessarily chooses zero resumptions. This keeps affine zero-resumption control inside the ordinary affine continuation-abandonment rule rather than adding another mode.

Handlers are lexical interpreter blocks, not first-class values. A handler block appears as part of a `handle ... with handler ...` application and creates one active handler frame. Reusable interpretation is expressed by an ordinary function that installs the lexical handler around a supplied computation. The residual effects and result provenance of that wrapper are ordinary function-contract facts; Eldude has no separate public `Handler<...>` value type.

## 20. Continuation and handler-frame safety reuse ordinary usage rules

For `affine` operations, the potentially abandoned continuation segment is treated semantically as a hidden value containing the frames and obligations between the operation and its matching handler delimiter. Zero resumption is legal only when abandoning that segment satisfies the common structural-exit law.

An active lexical handler frame also owns the values retained by its clauses for the entire `handle` evaluation. Resumption threads that frame through ordinary usage rather than making a second logical owner. At every `resume`, each non-`Dup` frame capture is **moved into the resumed computation** and is unavailable to code after that `resume` returns. Only `Dup` frame captures may remain available on both sides of a returning resumption. The resumed computation, including any re-entered operation or `return` clause, owns the moved frame obligations and must eventually consume, transfer, structurally own, or otherwise legally discharge every non-`Discard` obligation exactly once.

For a `tail` clause this transfer is natural because no code follows `resume`. A `once` or resuming `affine` clause may continue after `resume`, but its post-resume code is checked under the usage environment with all moved non-`Dup` frame captures unavailable. A zero-resumption affine path instead retains the frame locally and must discharge its non-`Discard` obligations itself.

This prevents deep re-entry or a `return` clause from consuming a linear handler capture and then returning control to an outer clause that still believes it owns the same capture. It does so without first-class handler multiplicity, `Fn`/`FnMut`/`FnOnce`-style handler families, or a separate continuation ownership system.

## 21. Expected failure is data

Recoverable failure uses:

```eldude
Result<E, T>
```

Error alternatives are ordinary nominal data, typically an `enum`:

```eldude
enum LoadError {
    IO(IOError),
    Parse(ParseError),
}
```

Eldude has no structural `error { ... }` set type in the 0.0.1 core. When APIs compose distinct nominal error types, they map them explicitly into a chosen nominal error type.

Postfix `?` performs identity propagation of a `Result<E,T>` to a compatible lexical `try` boundary or enclosing `Result<E,_>` function. It never performs programmer-defined conversion code, structural error-set injection, or widening implicitly.

`try` creates a lexical `Result` propagation boundary for one chosen nominal error type.

`Result` is the sole standard representation for routine expected failure. Dynamically scoped affine zero-resumption algebraic control remains available through `affine` effects when that control behavior is itself part of an abstraction, but it is not a second standard exception convention.

## 22. Defects are not errors or effects

Eldude has one explicit assertion form:

```eldude
assert condition;
```

Assertion failure is a nonrecoverable defect termination. It is not `Result`, not an algebraic effect, and cannot be caught by an Eldude handler. A function type does not promise defect-freedom; absence of `diverge` promises absence of admitted nontermination, not guaranteed normal production of the result value.

A defect is not a statically recoverable structural exit. The checker does not require arbitrary naked linear obligations to be discharged on a path that ends in a defect, because no Eldude continuation survives that path. Explicit structural owners such as `using` and `taskgroup` still perform their specified best-effort unwinding before the defect reaches the host diagnostic boundary. If a first defect is encountered while a non-defect structural outcome is pending, that defect becomes primary and the prior outcome becomes suppressed diagnostic context. Once a defect is primary, later defects encountered during structural discharge are secondary diagnostics. Reachable structural discharge continues unless divergence or process-level termination prevents progress.

Assertions are runtime checks only. They are never proof evidence required for type safety, region/access safety, usage safety, non-divergence, or optimizer correctness. Eldude deliberately has no build-erasable assertion construct whose removal could change ownership/effect behavior.

Eldude has no general-purpose `panic` facility.

## 23. Logging is an ordinary effect; diagnostics are data

Logging belongs in the standard library, conceptually:

```eldude
effect Log {
    tail emit(record: LogRecord) -> Unit;
}
```

It is not language magic, and assertions do not acquire a `Log` effect.

Errors may optionally implement a pure `Diagnostic` trait that produces structured diagnostic data. Error values remain data; logging remains an effect. `?` never logs automatically.

---

# V. State, access, regions, and resources

## 24. Mutable identity requires an explicit abstraction

Eldude separates two forms of mutable identity.

A nonduplicable mutable owner is mutated through exclusive call-scoped `mut` access. The bundled standard-library `DynArray<T,@r>` is the canonical example; the semantic category is not tied to that exact collection type. Forming a root `mut` grant requires compiler-recognized mutable-owner identity on a designated region-owned abstraction; being non-`Dup` is necessary for exclusive ownership but does not itself create mutable identity. Scoped projection may derive a `mut` grant to an arbitrary subvalue from an already valid parent-owner grant without making the subvalue a new root mutable owner. Mutable-owner status is not a user-implementable trait.

An aliasable cell is an explicit shared-state abstraction whose operations carry `state<@r>`. The bundled standard-library `Ref<T,@r>` is the canonical example; the core law is about aliasable region state, not that exact type name.

`mut` is not the mechanism for aliasable shared cells.

## 25. Temporary access is not borrowing

Function parameters may be:

```eldude
x: T          // ordinary value/ownership semantics
view x: T     // shared, non-consuming call-scoped access
mut x: T      // exclusive mutable-owner call-scoped access
```

Method calls preserve the same visibility at the call site:

```eldude
value.method(args)          // self
view value.method(args)     // view self
mut value.method(args)      // mut self
```

Dot syntax therefore does not silently manufacture a `view` or `mut` grant. Access-prefixed ordinary arguments and method receivers name in-scope bindings (including projected callback parameters), not arbitrary computed expressions; code binds a computed result first when it needs to grant access to that result. This keeps the access syntax context-free and consistent with the fact that grants are not reified values. These are permissions during one dynamic call. They are not values and cannot be stored, returned, captured, or reified.

`view` means shared non-consuming access, not observational immutability. An explicitly aliasable mutable abstraction such as `Ref` may still change state through effectful operations.

Eldude has no general `&T`, `&mut T`, borrow expression, or lifetime language.

## 26. Scoped projection replaces borrowed subobjects

When code must inspect a non-`Dup` subvalue without consuming it, nominal APIs project a `view` or `mut` grant into a callback:

```eldude
view values.with(index, fn(view item) {
    inspect(view item)
});
```

The projected grant exists only for that invocation and cannot escape.

Projection APIs should preserve ownership rather than force discardability when conditional invocation is the only obstacle. A standard library may therefore provide a form whose miss path returns the callback/obligation unchanged, and collection-specific multi-element projection combinators may prove non-overlap internally before invoking a callback. These are library-level ergonomic forms of the same scoped-access rule, not reference values or a second borrow system.

Eldude therefore does not need a first-class borrowed element or general non-owning slice type.

## 27. Regions are generative lexical state domains

```eldude
region scratch {
    ...
}
```

creates a fresh region identity `@scratch`.

A value may leave the region only when its type and capture/provenance summary do not retain `@scratch` and all region-local ownership obligations have been discharged.

The region eliminates its own `state<@scratch>` effect when the identity cannot escape.

Tracked provenance has an internal lexical retention horizon even though Eldude exposes no lifetime syntax. Freely aliasable mutable storage such as `Ref<T,@r>` may retain a value only when every lexical provenance captured by that value remains valid for at least the lifetime of `@r`; an outer cell therefore cannot be used to hide a shorter-lived region, taskgroup, effect instance, or foreign registration. This is a scope-order check, not a new user-visible lifetime language.

Regions identify mutable-state lifetime. They do not automatically mean stack, arena, allocator, or physical address stability.

## 28. Aliasable cells cannot contain undiscardable obligations

For the bundled aliasable-cell abstraction `Ref<T,@r>`, the payload rule is:

```eldude
T: Discard
```

Such a handle is aliasable and unrestricted. Reading by value additionally requires `T: Dup`. Replacement transfers the old value explicitly.

Linear payloads remain behind nonduplicable owners rather than inside freely aliased cells. This is the semantic rule; concrete cell types are standard-library/runtime choices.

## 29. Cleanup is explicit

`using` is Eldude's deterministic cleanup boundary:

```eldude
using (file = open(path)?) {
    ...
}
```

A `using` scope owns the cleanup responsibility for a resource that remains live at scope exit. Cleanup runs during normal exit, `return`, `?`, loop exits crossing the scope, affine zero-resumption control, cooperative cancellation, and defect unwinding.

Cleanup is entered in reverse acquisition order and is protected from cooperative cancellation.

Discarding an affine value does not run cleanup. `Discard` always means that abandonment itself has no hidden semantic effect.

## 30. `Cleanup` is one intrinsic protocol

Eldude has one user-implementable intrinsic cleanup trait, conceptually:

```eldude
intrinsic trait Cleanup<!e> {
    fn cleanup(self) ->{e} Unit;
}
```

Only non-`Dup` types may implement it. There is one coherent cleanup implementation for a nominal type.

Cleanup consumes the resource, returns exactly `Unit`, and cannot report recoverable failure. Meaningful fallible completion is an explicit operation such as `finish()` or `commit()`; cleanup is fallback discharge.

Cleanup may perform ordinary effects, may suspend while cancellation is masked, and may admit `diverge`. Cleanup is discharge-only control and is checked by the **same continuation-control envelope as ordinary code, evaluated under the cleanup cancellation mask**. The mask removes the cancellation-abandonment edge contributed by `suspend`; it does not neutralize residual `affine` control, so any affine family that may choose zero resumptions must be handled before leaving the cleanup invocation. No separate `cleanup-safe` effect classification exists. `using` guarantees entry of required cleanup during structural exit, not successful completion of cleanup that diverges.

Defects encountered during cleanup use the general structural-discharge precedence rule: a first defect supersedes any pending non-defect outcome, while later defects during an existing defect unwind are secondary diagnostics. If cleanup diverges, no guarantee is made that later cleanup or the prior control outcome can be reached.

---

# VI. Collections and generic data processing

## 31. Collections preserve usage obligations

The language-level rule is about **owning containers**, not particular collection implementations:

- a container preserves the `Dup`/`Discard` obligations of values it owns;
- reading an owned element by value while preserving the container requires `Dup`;
- discarding a displaced/filtered element requires `Discard`;
- a consuming transformation may work for arbitrary element types only when every obligation is transferred or structurally discharged;
- a recoverably fallible consuming operation over a potentially non-`Discard` input must return that ownership obligation on every failure path, discharge it structurally, or require `Discard`.

Concrete families such as `List<T>`, `TreeList<T>`, `LinkedList<T>`, `Array<T,N>`, `DynArray<T,@r>`, and owning slice/view types are standard-library choices, not separate core-language mechanisms. The Full Specification may define a bundled standard-library profile and its cost contracts, but changing one of those representations does not change Eldude's ownership semantics.

The standard library should make the common laws pleasant rather than exceptional. Search, split, projection, and fallible traversal combinators over linear data should preserve the unconsumed remainder or otherwise preserve every element on recoverable early exit. Generic effect-polymorphic traversals may use `where e: NonAbandoning` when they must retain non-`Discard` state across callback calls.

## 32. Indexing does not manufacture a borrow

Ordinary value-returning indexing requires duplicability.

For non-`Dup` elements, code either:

- consumes the collection through an ownership-transferring operation; or
- uses scoped projection to inspect/mutate an element without creating a reference value.

Fixed-shape arrays and dynamic sequences are standard-library abstractions. Their APIs may differ, but none may manufacture a hidden borrow or silently lose an ownership obligation.

## 33. Iterators are ownership-threaded state machines

The bundled standard iteration protocol does not depend on a borrowed mutable iterator. The protocol is a standard-library trait used by `for`, not a separate ownership mechanism.

Conceptually:

```eldude
enum Next<I, T> {
    Item(T, I),
    Done,
}

trait Iterator {
    type Item;
    fn next(self) -> Next<Self, Self::Item>;
}
```

Each step consumes the current iterator state and returns either completion or one element plus the next state.

For a linear collection, the iterator is linear and carries the remaining ownership obligation. An early control exit is legal only when the remaining iterator state can be legally discharged.

Because `next` returns `Self`, this static `Iterator` interface is intentionally not dynamically compatible with `any Iterator`.

---

# VII. Structured concurrency

## 34. Concurrency is not parallelism

`taskgroup`, `spawn`, and `await` express structured concurrency inside one Eldude execution domain.

Only one Eldude strand in a domain executes Eldude code at a time. Sibling strands interleave cooperatively.

Eldude currently has no source-level shared-memory parallelism model. The runtime may use multiple operating-system threads internally only when observable Eldude semantics are preserved.

This decision avoids a general `Send`, `Sync`, `Transfer`, or thread-affinity type axis.

User-directed multicore execution of ordinary Eldude code is outside the current language scope. Programs that require it must currently use host/native facilities. This is a deliberate version boundary, not a claim that parallel computation lacks concrete use cases. If Eldude later adds an explicit parallel-computation facility, that facility must define its own transfer and state-access boundary without retroactively turning ordinary `taskgroup` concurrency into shared-memory parallelism.

## 35. Interleaving occurs only at explicit semantic suspension points

A strand is not invisibly preempted during ordinary Eldude execution.

Interleaving may occur when the strand actually reaches a suspension point such as:

```text
await
explicit yield
suspending host wait
an operation whose implementation suspends
```

A compute-bound strand that never suspends can monopolize its execution domain. This is a consequence of the cooperative model, not hidden scheduler behavior.

## 36. Cancellation is cooperative structural control

Cancellation is delivered only when execution actually reaches an ordinary suspension point, and is masked only during explicitly specified structural discharge such as cleanup and taskgroup shutdown. Pure computation and synchronous handler execution are not implicit cancellation points. Eldude has no separate `cancellable` suspension category.

Cancellation is not a business result and is not added to every function's return type. Every reachable ordinary suspension point must therefore be statically legal as a cancellation structural exit under the common structural-exit law. A naked live linear obligation that has no valid structural discharge path across that suspension makes the program illegal rather than silently suppressing cancellation.

Cleanup and structural taskgroup shutdown are protected from cooperative cancellation while they discharge owned obligations.

## 37. `taskgroup` is the ownership boundary for children

A taskgroup owns all children created lexically within it. The group also retains the tracked capture/provenance obligations of live children and of completed-but-not-yet-disposed child results, so a discarded `Task` handle cannot hide a region, effect-instance, or foreign lifetime dependency.

On normal body completion, it waits for remaining children before returning.

When control exits early by `return`, `?`, affine zero-resumption control, outer cancellation, or defect, the group requests cancellation of outstanding children, drains them, performs their structured cleanup, and only then propagates the original control outcome.

A child returning `Result::Err` has merely produced data. It does not automatically fail or cancel the group.

## 38. Spawned results are safely abandonable

`spawn` requires the child result type to satisfy:

```text
T: Discard
```

A child may own linear resources internally, but it cannot export an abandonment-sensitive obligation as its asynchronous result. In particular, safe `spawn` cannot be used to construct a linear resource in a child and transfer that resource to its parent as the task result.

This is a deliberate expressiveness boundary. It makes structural cancellation sound without a task-result finalization framework. If concrete programs later require non-`Discard` task results, the task-result ownership model must be redesigned so that a completed but unobserved result remains a tracked obligation; that capability must not be approximated by silently discarding the result or by introducing a general `Send`/`Transfer` predicate.

## 39. Task handles are unique observation/control rights

`Task<T>` is never `Dup` and is `Discard` because `T: Discard` at every spawn site.

```eldude
await task
```

consumes the handle and returns exactly `T`.

```eldude
task.cancel();
```

consumes the handle and requests cancellation without suspending or waiting for termination.

Discarding a task handle has no semantic effect. The taskgroup, not the handle, owns child lifetime.

Task handles retain compiler-tracked provenance for their creating taskgroup and therefore cannot escape it. No source lifetime parameter is required.

## 40. Child effects belong to the lexical taskgroup

`spawn` is a language form valid only lexically inside `taskgroup`.

The child's effects are accounted for by the enclosing taskgroup, not stored in `Task<T>` and not performed by the parent at the `spawn` expression. The taskgroup likewise retains the child's capture/provenance summary for lifetime checking until that child/result obligation has structurally ended.

Task completion dependencies participate in the ordinary non-divergence analysis. More generally, any opaque indirect control dependency—such as an opaque task, a callable loaded from externally supplied mutable state, a retained opaque callback, or an opaque handler/control edge—admits `diverge` unless the current semantic contract proves a well-founded terminating dependency. Eldude prefers this conservative rule to implementation-body inspection.

## 41. Handler inheritance follows the taskgroup boundary

A taskgroup records the handler environment that lexically encloses the taskgroup itself. A child may resolve an effect through such an inherited handler only when the relevant active handler frame is `Dup`; semantically the child receives its own reusable frame installation for the same lexical effect-instance identity, with captured values duplicated only by ordinary `Dup`. If a child effect would resolve to a non-`Dup` enclosing handler frame, the spawn/composition is rejected unless an appropriate handler is explicitly installed inside the child computation. An unconstrained open child effect row is checked conservatively against ambient non-`Dup` handlers.

A handler entered only by the parent after the taskgroup begins is parent-strand-local unless the handler is explicitly placed inside the child computation. Shared mutable handler state uses ordinary explicit aliasable state such as `Ref`; handler inheritance does not create hidden shared ownership.

`spawn` never snapshots an arbitrary transient dynamic handler stack.

## 42. Structured concurrency patterns are library operations

Eldude needs no `race` keyword and no general public task-handle `select` primitive.

A standard `race` combinator creates a nested taskgroup, starts its branches, waits for the first completed result, requests cancellation of the others, drains the nested group, and returns the winner. Racing is not transactional. Effects performed by losing branches remain performed. `Result::Err` is an ordinary completed result and may therefore win a race.

The same principle applies to common `join`, timeout, and bounded concurrent-map patterns: standard-library combinators own nested taskgroups internally and preserve the ordinary `spawn` result, effect, cancellation, handler-inheritance, provenance, and drain rules. Convenience at this layer does not require a first-class taskgroup capability or detached tasks.

---

# VIII. Systems boundary

## 43. Unsafe code grants narrow permissions

`unsafe` does not disable Eldude's checker.

Inside unsafe code, ordinary typing, effects, usage, regions, captures, non-divergence, and task structure still apply. Only specifically designated unsafe operations become legal.

An `unsafe fn` places documented proof obligations on its callers. Unsafe operations inside its body still require explicit `unsafe { ... }` blocks.

`unsafe` is a static trust boundary, not a runtime effect.

## 44. Ordinary values are never pinned

Eldude has no general `Pin`, `Pinned<T>`, `Unpin`, or immovable type property.

Foreign identity and stable native memory are separate FFI concerns:

- an opaque foreign callback token uses a runtime/library rooting handle; `ffi::Handle<T>` is the bundled conceptual example, and the underlying Eldude value may move;
- dereferenceable stable native storage uses an explicit native-allocation owner; `ffi::Box<T>` is the bundled conceptual example;
- pointers valid only for one call use scoped marshalling. Each safe marshalling scope creates a fresh compiler-internal foreign provenance identity whose horizon is the callback's dynamic extent. Temporary native-view values retain that identity transitively, so closures, containers, erased packages, outer cells, or other wrappers cannot hide the temporary view beyond the scope. A nested structured computation is permitted only when it fully resolves before the marshalling callback returns.

This scoped provenance is an instance of Eldude's existing capture/provenance model, not a source lifetime or pinning system. Provenance proves that the temporary native view cannot outlive the marshalling scope; the wrapper separately guarantees that any dereferenceable address it exposes remains physically valid for that dynamic interval, by representation stability, temporary native storage, copying, or another audited implementation technique. Raw-pointer operations remain unsafe; unsafe code that deliberately retains such a pointer assumes the corresponding native lifetime and address-stability proof obligations.

Safe self-referential ordinary Eldude values are not a general language feature.

## 45. Foreign threads do not silently become Eldude strands

A synchronous same-domain foreign callback may re-enter Eldude according to its audited FFI contract. Callback contracts must state invocation cardinality—whether the callback may be skipped or repeated—and whether the same registration may be re-entered before a prior invocation returns. Ordinary `Discard`/`Dup` rules govern the callback environment: possible skipping requires discardability, repeated invocation requires duplicability, and re-entry of the same registration likewise requires a duplicable environment.

An ordinary safe same-domain synchronous callback executes beneath an internal **foreign-control barrier**. While that barrier is active, callback execution must not reach an ordinary `suspend` point, and an algebraic operation may resolve only to a handler installed on the callback side of the barrier. Handler lookup does not cross the waiting foreign frame, regardless of whether the operation is `tail`, `once`, or `affine`. `NonAbandoning` does not weaken this rule: non-abandoning operations may still require continuation capture and resumption. Pending cooperative cancellation remains pending until execution has returned through the foreign call to an ordinary Eldude cancellation-delivery point.

A safe synchronous callback that can defect must have an audited defect rendezvous: the runtime/native shim records the defect, performs callback-local structural unwinding, returns through the foreign call using a contractually valid private control path, and resumes Eldude defect unwinding only after control reaches an Eldude boundary. Any native sentinel used only for this rendezvous is not exposed as a normal recoverable application result. A foreign API that cannot provide such a rendezvous requires an unsafe/native adapter; Eldude defects and foreign exceptions do not unwind arbitrarily through foreign frames.

A host/native adapter may define a separately audited stack-preserving synchronous-callback protocol that permits `suspend`. Such a protocol must define native-stack lifetime, runtime rooting, resumption thread/fiber behavior, pointer stability, reentrancy, cancellation rendezvous, defect rendezvous, and shutdown. Permission to suspend does not by itself permit algebraic continuation capture through the foreign frame; cross-foreign-frame algebraic control remains outside the ordinary safe model.

An asynchronous callback from another native thread is posted to an Eldude execution domain and runs later as ordinary Eldude work. It does not execute arbitrary Eldude code concurrently on the foreign thread. A retained callback registration has an explicit lifetime owner that deregisters and drains accepted/in-flight callback work before releasing captured Eldude state.

Foreign APIs requiring synchronous arbitrary-thread execution require an explicit unsafe/native adapter with audited runtime attachment and synchronization semantics.

## 46. The host is the outer runtime boundary

Every executable or embedding configuration selects exactly one host/runtime integration contract, but host selection is **root/build metadata rather than ordinary Eldude source syntax**.

The host supplies startup, external services/effect implementations, event/scheduler integration, allocation/runtime facilities, native adapters, and lifecycle.

A conforming execution domain has a minimal **runnable-strand progress** rule: when the current strand yields/terminates and at least one Eldude strand in that domain is runnable, scheduling itself cannot stutter forever; a runnable strand is selected in the next scheduler transition. This is not a fairness, latency, or priority guarantee. Delays waiting for external events remain governed by the relevant host/foreign finite-return contracts and therefore admit `diverge` when termination is not justified. A host/runtime implementation may choose any scheduling policy consistent with this minimum progress rule.

Ordinary libraries do not receive an ambient `Host` capability object and do not acquire separate host-requirement predicates. They expose required behavior through ordinary types, effect rows, and audited foreign contracts. Application or embedding roots carry a root-only host/embedding contract describing startup, exported entry points, runtime integration, native trust assumptions, and conformance to the scheduler/event progress assumptions used by Eldude's non-divergence semantics. Root conformance is checked only at the application/embedding boundary; that contract is not an ambient library capability and cannot change ordinary call legality beyond the library's exported semantic contracts.

# IX. Compilation and tooling

## 47. Separate compilation is a language property

A module must be semantically checkable from:

- its own source;
- canonical interfaces of direct imports.

Imported implementation bodies are not semantic prerequisites.

A private body change that preserves the canonical semantic interface does not require downstream semantic rechecking.

## 48. Canonical interfaces contain every client-relevant obligation

Interfaces include, as applicable:

- nominal identities and visible definitions;
- types and kinds;
- effect rows plus canonical effect-family control summaries sufficient to derive their continuation-control envelope;
- callable-environment captures and result-capture relationships;
- `Dup`/`Discard` guarantees;
- compiler-recognized mutable-owner status where applicable;
- regions and compile-time naturals;
- trait and GAT declarations;
- coherent implementation headers;
- residual effect contracts of public functions that install lexical handlers;
- cleanup implementations and effect rows;
- dynamic-trait requirements;
- foreign/ABI semantic contracts;
- root-only host/embedding contracts when the artifact itself is an application or embedding root.

Ordinary library interfaces contain no separate host-requirement predicate. Every client-validity fact in the canonical machine interface must also have a deterministic human-readable generated rendering. Facts already expressible in ordinary Eldude syntax use that syntax; inferred facts such as result-capture relationships and mutable-owner status use normalized generated semantic clauses rather than opaque compiler variables or lifetime inequalities. Canonical interface notation is a distinct toolchain grammar: generated `semantic { ... }` clauses are not silently treated as author-written source syntax. Generated unordered rows and sets use one deterministic textual ordering so equivalent public semantics produce stable signatures and diffs.

Optimization bodies and specialization hints are separate non-semantic metadata.

## 49. Generic code is separately compilable

Eldude does not require whole-program monomorphization.

Implementations may use shared generic code, dictionaries, specialization, monomorphization where profitable, or combinations of these, provided semantic checking remains separate.

## 50. Diagnostics and formatting are part of the design

Diagnostics should explain source-level obligations and retention paths, not expose implementation machinery. Derived effect-control failures should name the concrete source of abandonment—for example `suspend` or an `affine` operation—and should suggest `where e: NonAbandoning` when that is the intended generic contract rather than exposing solver internals.

The toolchain includes deterministic formatting, stable interface hashing, incremental checking, generated public signatures that render every client-relevant semantic fact in source-level terminology, isolated test execution conventions, and canonical machine-readable FFI binding metadata that keeps ABI facts separate from audited semantic contracts.

Testing does not require special core-language syntax.

---

# X. Deliberate non-goals

The current Eldude design deliberately excludes:

- a Rust-style general borrow checker or lifetime language;
- general safe reference types;
- first-class borrowed slices into mutable owners;
- local reassignment;
- implicit currying or partial application;
- labelled/default parameters;
- structural records;
- `some Trait`;
- explicit general existential syntax;
- type-level lambdas and unrestricted type-level recursion;
- capability types;
- surface uniqueness qualifiers;
- implicit effectful destruction;
- general-purpose panic/exception semantics;
- a separate `abort` resumption mode (`affine ... -> Never` is used instead);
- structural `error { ... }` set types or implicit error-set widening;
- many-shot algebraic resumption in the 0.0.1 core;
- unchecked implicit failure conversion;
- overlapping/incoherent traits;
- mandatory whole-program monomorphization;
- `async fn` or a `Future` language layer;
- `Send`/`Sync`/`Transfer`-style ordinary type predicates;
- source-level shared-memory parallelism or user-directed multicore execution of ordinary Eldude strands;
- pinning or immovable ordinary values;
- detached tasks as a core primitive;
- safe `spawn` results that carry non-`Discard` ownership obligations across the task boundary;
- user-defined operators/precedence;
- ambient executable module initialization;
- first-class handler values/types in the 0.0.1 core;
- source-level host-selection declarations;
- syntax whose only current justification is convenience.

These omissions are not claims that the corresponding capabilities are useless. They are statements about where Eldude chooses to place complexity. Some are deferred because the existing model is expected to cover the motivating programs; many-shot resumption is specifically deferred until concrete workloads justify continuation duplication; others, notably user-directed parallel execution and non-`Discard` spawned results, are explicit scope boundaries of the current design.

---

# Conclusion

Eldude's intended shape is a strict value language with explicit behavior and explicit ownership-sensitive boundaries:

```text
immutable values
fixed-arity functions
nominal algebraic data
Dup / Discard usage
tracked captures and result provenance
visible effects with derived continuation-control checking
checked divergence
explicit nonrecoverable defects
common recoverable structural-exit checking
lexical algebraic handlers
call-scoped view / mut access
generative regions
explicit using / Cleanup
usage-preserving standard collections and ownership-threaded iteration
cooperative structured concurrency
narrow unsafe / FFI boundaries
one host boundary
canonical separate-compilation interfaces
```

The design criterion is not whether each feature is individually elegant. It is whether the complete system remains coherent when effects, resources, handlers, cancellation, state, generic abstraction, and foreign code meet in the same program.
