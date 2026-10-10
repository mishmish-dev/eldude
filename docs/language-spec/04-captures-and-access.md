# Chapter 4 — Closures, captures, and scoped access

[Specification index](../language-specification.md) · Previous: [3. Traits and dynamic abstraction](03-traits.md) · Next: [5. Effects, termination, and failure](05-effects-and-failure.md)

This chapter explains what a callable retains and how a function temporarily inspects or mutates a value without creating reference values.

**Prerequisites:** [2. Types and ownership](02-types-and-ownership.md), [3. Traits and dynamic abstraction](03-traits.md).

The numbered rules are normative under the [specification conventions](../language-specification.md). Examples are illustrative snippets; names and omitted bodies may stand for surrounding program or library context.

## B.4 Linear closure

```eldude
linear struct File;

let closeLater = fn() {
    close(file);
};

closeLater();
// second call is illegal: callable instance was consumed
```

## In this chapter

- [12. Function-value capture semantics](#12-function-value-capture-semantics)
- [13. Captures](#13-captures)
- [14. Call-scoped access](#14-call-scoped-access)
- [15. Scoped access projection](#15-scoped-access-projection)

## 12. Function-value capture semantics

### 12.1 Capture by value

Closures capture owned values by value.

```eldude
let f = fn() {
    use(resource);
};
```

If `resource` is non-`Dup`, construction moves that obligation into the closure.

`view` and `mut` grants cannot be captured.

### 12.2 Function capture type

A first-class callable may expose retained obligations:

```eldude
fn() ->{fs} Bytes captures {file}
```

Effects answer what may happen during invocation. Captures answer what the callable retains while it exists.

Omitting a capture clause means no tracked capture obligation; ordinary immutable unrestricted data need not be listed merely because it is stored in the environment.

### 12.3 Callable usage

Callable usage derives from its capture environment.

A closure/handler whose tracked environment is unrestricted is unrestricted. If its environment is affine, it is affine. If it retains a linear obligation, it is linear.

Calling a function value consumes one logical instance of the callable value. Therefore:

- an unrestricted callable may be invoked repeatedly;
- an affine callable may be invoked at most once;
- a linear callable must be invoked exactly once, transferred to another owner, or consumed by an explicitly specified ownership-preserving structural-discharge protocol before the enclosing completed path ends. This last alternative is available only when the callable representation/interface or an audited intrinsic provides that operation ([§56.2.1](10-host-and-ffi.md#5621-lifecycle-cardinality-and-undelivered-obligations)); ordinary function values have no generic environment-extraction or discard operation.

Eldude has no separate `Fn`, `FnMut`, `FnOnce`, `once fn`, or affine-function arrow.

### 12.4 Higher-order generic constraints

A higher-order implementation that may invoke a callback multiple times requires the callback environment to be duplicable. One that may skip and abandon the callback requires discardability; returning the callback obligation or structurally consuming it is a different ownership-preserving contract. For retained callbacks the complete lifecycle, including close/cancellation, determines this requirement ([§56.2](10-host-and-ffi.md#562-asynchronous-callback-from-another-native-thread)).

Capture-row parameters may therefore carry usage constraints conceptually of the form:

```eldude
fn map<A, B, ..C>(
    f: fn(A) -> B captures {..C},
    values: List<A>,
) -> List<B>
where ..C: Dup + Discard;
```

The constraint means every retained obligation represented by the capture row admits the required permission. `where ..C: Dup` and `where ..C: Discard` are the canonical surface forms for structural usage constraints on a capture-row parameter.

Effect-polymorphic repeated-callback APIs may constrain the already-derived continuation-control property when they must retain non-`Discard` obligations across calls. For example:

```eldude
fn forEach<T, !e, ..C>(
    values: List<T>,
    f: fn(T) ->{| e} Unit captures {..C},
) ->{| e} Unit
where e: NonAbandoning,
      ..C: Dup + Discard;
```

`NonAbandoning` is the intrinsic effect-row constraint of [§17.3](05-effects-and-failure.md#173-derived-continuation-control-envelope). It does not constrain which ordinary effects may occur except through their already-declared continuation behavior.

## B.3 Repeated callback

```eldude
fn map<A, B, ..C>(
    f: fn(A) -> B captures {..C},
    values: List<A>,
) -> List<B>
where ..C: Dup + Discard
{
    ...
}
```

`map` may invoke `f` zero times for an empty collection and multiple times otherwise. This pure form can preserve arbitrary linear input/output obligations because the callback cannot abandon the surrounding continuation.

An effect-polymorphic linear traversal may instead state the derived control requirement directly:

```eldude
fn forEach<T, !e, ..C>(
    values: List<T>,
    f: fn(T) ->{| e} Unit captures {..C},
) ->{| e} Unit
where e: NonAbandoning,
      ..C: Dup + Discard
{
    ...
}
```

An unconstrained open row remains conservatively potentially abandoning.

## 13. Captures

### 13.1 Purpose

Captures track retained obligations whose omission could permit illegal escape or invalid duplication/discard.

Tracked captures include at least:

- linear or affine owned resources;
- region identities retained through region-indexed state;
- taskgroup provenance retained by task handles;
- lexical effect-instance identities;
- foreign/runtime provenance whose lifetime matters;
- values transitively containing such obligations.

Ordinary unrestricted immutable data is not listed merely because it is stored.

### 13.2 Transitivity

Containers, closures, dynamic trait packages, task handles, and other first-class values preserve the tracked captures of their contents. Active handler frames separately preserve every value/provenance retained by their lexical clauses for the duration of the `handle` expression.

Wrapping a value cannot hide an invalid escape.

### 13.3 Capture polymorphism

Open capture sets use capture-row parameters:

```eldude
fn defer<A, !e, ..C>(
    f: fn() ->{| e} A captures {..C},
) -> fn() ->{| e} A captures {..C};
```

### 13.4 Conservative result-capture bounds

Callable-environment captures and result captures are distinct facts. Every function or method semantic contract has a finite result-capture bound `ResultCaptureBound`: a union of whole argument/environment capture summaries, capture-row parameters, and named provenance atoms. Application substitutes the actual summaries and takes their union, together with captures required by the result type. There is no component-sensitive or executable transformer.

The compiler may infer which whole sources a body can retain. Retaining any part of an argument widens to that argument's whole summary at the callable boundary; retaining part of the callable environment similarly widens to the whole environment. A public or first-class callable MUST carry the resulting stable bound. If no sound bound is expressible in this algebra, the definition is rejected. For a bodyless declaration without a checked or audited narrower bound, include every argument and the callable environment; the provider must still prove or audit that no additional provenance can be retained. Clients never inspect an imported body to recover precision.

For an access-mode argument, the source describes the accessed value, not the grant or its authority. Legally copying a duplicable field ([§8.1](02-types-and-ownership.md#81-products)) can return an ordinary value, but its published bound uses the whole accessed-value summary. Returning an erased field retaining `@r` through `view holder` therefore preserves `@r` even when the holder itself is non-`Dup`. Grant authority cannot escape.

A result whose instantiated type satisfies `CaptureFree` ([§9.6](02-types-and-ownership.md#96-capture-free-types)) has an empty summary. The evidence must follow from complete structural types, an ordinary `CaptureFree` bound, or a published compiler-derived/audited profile. An unconstrained type variable, an unknown opaque representation, or `Dup + Discard` alone does not establish it. In particular, `Ref<Int,@r>` and `DynArray<Int,@r>` retain `@r`. Otherwise use the whole published bound without selectively deleting atoms based on the result's apparent fields. Bounds are retention upper bounds, not ownership transfers: they never create, duplicate, discard, or revive a resource obligation.

This conservative rule intentionally rejects some safe escapes. A function returning the first member of an opaque-value pair publishes the whole pair's captures, so a scope dependency in the unused second member can prevent the result from escaping. No source lifetime language is introduced.

<a id="135-retention-horizons"></a>

### 13.5 Aliasable cell payloads

Every lexical provenance atom has an internal validity horizon determined by lexical scope, even though no outlives syntax is exposed. A retaining owner may safely retain a provenance atom only while that atom remains valid.

Freely aliasable mutable storage cannot retroactively change existing aliases' capture summaries. `Ref<T,@r>` therefore requires `T: CaptureFree + Discard`: construction and every payload-replacing write MUST establish this payload-type restriction. The guarantee covers every value of `T`, including future writes. The handle itself retains `@r` and is not `CaptureFree`.

Scoped references, task handles, and closures retaining scoped state cannot be cell payloads, even when their provenance remains valid longer than the cell. A generic setter uses the ordinary `T: CaptureFree + Discard` bound; checking it introduces no inferred callable lifetime preconditions or outlives solver.

Mutable storage that retains scoped contents uses exclusive ownership and `mut`, with the conservative whole-owner capture accounting of [§13.6](#136-canonical-interfaces-and-conservative-mutation). Ordinary lexical validity and non-escape checks continue to apply to those owners and all other scoped values.

### 13.6 Canonical interfaces and conservative mutation

Public capture bounds use only whole argument/environment sources, existing capture-row parameters, and named provenance atoms. The checker, machine serialization, human-readable rendering, and semantic hash use the same finite union. Generated notation is interface/diagnostic notation, not author-written source syntax:

```text
result-captures <= { captures(cell), captures(callback), ..C, @r }
```

`captures(x)` denotes the named argument's whole summary, `captures(parameter(n))` its canonical positional spelling, and `captures(..)` the whole callable environment. Access-mode sources describe accessed values. `..C` is an existing capture-row parameter, and a named atom such as `@r` may appear directly. `{}` is an empty bound and cannot override captures required by the result type. Duplicate union entries are removed. The initial core has no capture-source projections, separate stored-payload summaries, or post-call payload contracts.

Construction, erasure, moves, and branch joins preserve sound whole-value summaries. At a callable boundary, any capture-bearing component extracted from a returned aggregate inherits its whole summary; a statically capture-free component remains capture-free. Local checking may know more, but cannot publish or recover finer imported component bounds.

Intrinsic task metadata still distinguishes a task's owning group from its child's result captures ([§§41.2](09-concurrency.md#412-taskgroup-provenance), [67.4](11-formal-semantics.md#674-await)), so direct lexical `spawn`/`await` can return a child result without retaining the task's own group. This is not a public payload selector. Once a task is described by an abstract whole-value bound, including as a callable parameter/result or a component of an abstracted aggregate, its child-result bound MUST also be widened by that whole-value bound. Later `await` cannot recover the discarded precision; only a provably capture-free result can normalize to an empty summary. Thus forwarding a task through a helper can conservatively retain extra scope dependencies in its awaited result.

Every call with exclusive `mut` access conservatively grows each surviving accessed owner's whole summary by the pre-call summaries of all arguments and the callable environment, including other accessed values and intrinsic owner identities. If the types or audited builtin profile prove the writable storage can hold only capture-free values, no additional retained captures are introduced; the owner's existing summary is still preserved. Otherwise the union rule applies even when the call returns `Unit` or its body is available. Forwarded and projected grants update the containing owner. Removing or replacing a value does not shrink this bound.

The mutation rule applies on every normal or continuing structural exit where the owner survives, including recoverable failures and handler-mediated exits. A callee must also check every write and reject retention of locally introduced provenance beyond its valid scope; a caller-side union cannot excuse such an escape. Freely aliasable cells enforce [§13.5](#135-retention-horizons)'s `CaptureFree + Discard` payload-type restriction, so their writes cannot add captures to existing aliases. Ownership and grant-authority checks remain independent.

`DynArray<T,@r>::freeze` consumes the mutable owner and preserves element order. If `T` is provably capture-free, its `List<T>` result is capture-free and may leave `@r`. Otherwise the result conservatively retains the whole source summary, including `@r`, even if its elements actually depend only on outer scopes. The same rule applies through wrappers and generic instantiation. Freezing never subtracts a region from a mixed capture set; allocation reuse is permitted only when the resulting storage lifetime is valid.

### 13.7 Diagnostics

Illegal escape diagnostics SHOULD show a concrete retention path, for example:

```text
result -> closure -> parser -> Ref<State,@scratch> -> @scratch
```

rather than only an internal capture variable.

When conservative widening causes the rejection, diagnostics SHOULD identify the whole argument, environment, or mutable-call bound that introduced the dependency. They must not present an upper-bound dependency as a proven runtime retention path.

## 14. Call-scoped access

### 14.1 Parameter modes

Eldude has three parameter/receiver modes:

```eldude
x: T          // ordinary value/ownership semantics
view x: T     // shared non-consuming access
mut x: T      // exclusive mutable-owner access
```

Ordinary calls spell access on the binding argument (`f(view x)`, `f(mut x)`). Method calls spell the same access before the receiver binding (`view x.method()`, `mut x.method()`); an unprefixed `x.method()` is a consuming/value `self` call. Access markers do not apply to arbitrary computed expressions; bind such a result with `let` first.

### 14.2 `view`

`view` grants non-consuming shared access for the dynamic duration of one call.

The callee cannot store, return, capture, transfer, or consume ownership through the grant.

`view` is usually redundant for a statically unrestricted value and SHOULD be diagnosed when it conveys no additional obligation.

`view` does not mean observational immutability. A value such as `Ref<T,@r>` may represent explicitly shared mutable state and may change through effectful operations accessible from aliases.

### 14.3 `mut`

`mut` grants exclusive in-place access for one dynamic call. A root grant formed directly from an owned value requires the intrinsic mutable-owner judgment from [§9.5](02-types-and-ownership.md#95-mutable-owner-status); non-duplicability alone is not sufficient. A projected grant produced from an already active parent `mut` grant may target an arbitrary subvalue type and retains the parent owner identity/projection path.

The grant cannot be stored, returned, captured, or reified.

`mut` is not a general mechanism for aliased shared state. Shared mutable identity is represented by explicit types such as `Ref`.

`mut` carries call-scoped state authority as well as exclusive access. Its effect accounting is normative:

- Forming a root grant from an owned value satisfying `MutableOwner<T,@r>` MUST add `state<@r>` to the enclosing call expression's effects, regardless of the callee's written row. This is an upper bound even if the callee does not update the value or a conditional projection misses.
- A callee's `mut` parameter receives the caller-supplied grant and its authority. In-place updates to the granted storage, including updates through derived projections, require that authority but add no separate state entry to the callee's residual row. The parameter need not expose the parent region in its type or declare a region parameter for this purpose.
- Forwarding an active grant into another call, or deriving a projected grant, preserves its parent owner, region, projection path, and state authority. It does not form a new root grant or add a state effect solely for supplying that access. The original root charge remains in the enclosing computation.
- Supplied authority covers only the granted storage. Operations on independent mutable identities, including an aliasable `Ref` reached through the granted value, retain their ordinary effects even when those identities occupy the same region. Creating a new owned root grant also requires its own state accounting. Every effect explicitly admitted by an invoked callable's row MUST be propagated normally; `mut` never subtracts a declared state entry.

For example, projecting an element of `DynArray<DynArray<Int,@s>,@r>` preserves the outer grant's `@r` authority for the element slot. It does not confer authority over the inner array's independent `@s` identity. Mutating that identity retains `state<@s>` through the inner array API's ordinary effect contract; it cannot be classified as a row-free slot update merely because the inner owner was reached by projection.

Every callee body MUST be valid under any supplied grant admissible for its parameter modes/types, including a projection whose parent region differs from a region named by the target type. Knowing that the parameter type has `MutableOwner<T,@s>` status does not establish that the supplied grant is rooted at that independent owner or authorize its state outside the granted storage.

Thus `fn(mut T) ->{| e} R` declares additional effects under its explicit access requirement. An empty row permits updates through the supplied grant; invocation on an owned root still admits `state<@r>`. This interpretation applies uniformly to ordinary parameters, callbacks, inherent methods, and statically or dynamically dispatched `mut self` methods. It is not a general state-effect handler or erasure rule: an accounted state entry is eliminated only by its non-escaping region boundary.

### 14.4 Access intervals

An active `view` or `mut` grant remains active for the full dynamic call interval, including while an algebraic operation suspends the call and its handler executes.

A conflicting grant to the same mutable owner cannot coexist during that interval. An `affine` operation whose zero-resumption would abandon an active access interval is legal only when the common continuation-abandonment check permits that exit.

### 14.5 No general borrow language

Safe Eldude has no:

```text
&T
&mut T
borrow expression
address-of expression
lifetime parameter
```

Raw pointers exist only at the unsafe/FFI boundary.

## 15. Scoped access projection

### 15.1 Motivation

A non-`Dup` subvalue must sometimes be inspected without transferring ownership. Eldude does not solve this by returning a borrowed reference.

### 15.2 Projection rule

A nominal API may project an existing access grant into a callback invocation:

```eldude
fn with<T, R, !e, ..C>(
    view values: List<T>,
    index: Int,
    f: fn(view T) ->{| e} R captures {..C},
) ->{| e} Option<R>
where ..C: Discard;
```

For a mutable owner:

```eldude
fn withMut<T, @r, R, !e, ..C>(
    mut values: DynArray<T, @r>,
    index: Int,
    f: fn(mut T) ->{| e} R captures {..C},
) ->{state<@r> | e} Option<R>
where ..C: Discard;
```

The projected `view`/`mut` grant exists only during the callback invocation and cannot escape. A projected `mut T` grant carries the parent mutable owner's identity plus a non-overlapping projection path; it does not assert that `T` is independently a root mutable owner.

The callback receives the parent's state authority under [§14.3](#143-mut), so updates through the projected grant need not add `state<@r>` to `e`. The explicitly declared `state<@r>` on `withMut` remains a conservative API effect even when its receiver is an existing grant. At a root call, the declared state requirement and the root-grant charge use the same ambient state slot ([§16.5](05-effects-and-failure.md#165-scoped-row-equality-inference-and-weakening)). The same accounting applies to ownership-preserving and multi-element mutable projection forms.

### 15.3 Conditional invocation and callback usage

If an API may choose not to invoke a callback, the callback must be discardable. If it may invoke the callback multiple times, the callback must be duplicable.

These requirements arise from ordinary `Dup`/`Discard` checking, not from a separate callback-kind system.

### 15.4 Ownership-preserving conditional projection

The `with`/`withMut` forms above are convenient when the callback is `Discard`: a failed lookup may skip it. Standard collection APIs SHOULD also provide an ownership-preserving conditional form for callbacks that retain non-`Discard` obligations. Its miss path returns the callback value unchanged rather than abandoning it. Conceptually:

```eldude
enum Projection<R, F> {
    Found(R),
    Missing(F),
}

fn withPreserving<T, R, !e, ..C>(
    view values: List<T>,
    index: Int,
    f: fn(view T) ->{| e} R captures {..C},
) ->{| e} Projection<
    R,
    fn(view T) ->{| e} R captures {..C}
>;
```

The same principle applies to mutable-owner projection. No `..C: Discard` constraint is required merely for conditional invocation because the missing branch returns the callable and therefore preserves its obligations. The exact standard-library names are not a core-language requirement.

### 15.5 Multi-element projection

Collection abstractions SHOULD provide scoped multi-element projection when they can prove the required alias relation internally. Representative forms include:

```eldude
fn with2<T, R, !e, ..C>(
    view values: List<T>,
    left: Int,
    right: Int,
    f: fn(view T, view T) ->{| e} R captures {..C},
) ->{| e} Option<R>
where ..C: Discard;

enum ProjectionError {
    Bounds,
    AliasedIndices,
}

fn withMut2Distinct<T, @r, R, !e, ..C>(
    mut values: DynArray<T, @r>,
    left: Int,
    right: Int,
    f: fn(mut T, mut T) ->{| e} R captures {..C},
) ->{state<@r> | e} Result<R, ProjectionError>
where ..C: Discard;
```

The mutable form invokes the callback only after proving both indices are valid and denote non-overlapping projections; equal/conflicting indices produce the ordinary failure result. Ownership-preserving variants may return the callback on failure as in [§15.4](#154-ownership-preserving-conditional-projection). These APIs reduce callback nesting without creating reference values or a general borrow language.

### 15.6 No general first-class non-owning slice

Eldude does not currently define a general `Slice<T,@r>` or equivalent first-class view into a mutable owner's interior. Such a type would require invalidation rules equivalent to a long-lived borrow discipline.

Owning immutable subviews may be provided by library types when their ownership and usage semantics are explicit. Mutable-owner interior access uses scoped projection.

---

[Specification index](../language-specification.md) · Previous: [3. Traits and dynamic abstraction](03-traits.md) · Next: [5. Effects, termination, and failure](05-effects-and-failure.md)
