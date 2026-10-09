# Chapter 7 — Regions, mutable state, and cleanup

[Specification index](../language-specification.md) · Previous: [6. Handlers and resumption](06-handlers.md) · Next: [8. Collections and iteration](08-collections.md)

This chapter combines region-local mutable identity with explicit resource ownership and cleanup.

**Prerequisites:** [2. Types and ownership](02-types-and-ownership.md), [4. Closures, captures, and scoped access](04-captures-and-access.md), [5. Effects, termination, and failure](05-effects-and-failure.md), [6. Handlers and resumption](06-handlers.md).

The numbered rules are normative under the [specification conventions](../language-specification.md). Examples are illustrative snippets; names and omitted bodies may stand for surrounding program or library context.

## B.5 Region-local mutation

```eldude
fn encode(values: List<Byte>) -> List<Byte> {
    region scratch {
        let out: DynArray<Byte, @scratch> = DynArray::new();

        for value in values {
            mut out.push(value);
        };

        out.freeze()
    }
}
```

`state<@scratch>` is eliminated because no result/capture retains `@scratch`.

## In this chapter

- [27. Regions](#27-regions)
- [28. Mutable abstractions](#28-mutable-abstractions)
- [29. Resource usage](#29-resource-usage)
- [30. `Cleanup`](#30-cleanup)
- [31. `using`](#31-using)

## 27. Regions

### 27.1 Region introduction

A lexical region is introduced by:

```eldude
region scratch {
    ...
}
```

This creates a fresh region identity written:

```eldude
@scratch
```

The identity is generative: two different executions or lexical introductions denote distinct abstract regions even when the same source spelling is reused in different scopes.

### 27.2 Region parameters

Generic code may abstract over a region:

```eldude
fn size<@r>(view buffer: DynArray<Byte, @r>) ->{state<@r>} Nat;
```

There is no region subtyping or source-level outlives relation.

### 27.3 Region state effect

Operations observing or mutating region identity use:

```text
state<@r>
```

`state<@r>` is an intrinsic unhandleable effect. It cannot be intercepted by `handler`.

A region boundary eliminates every `state<@r>` entry for its own fresh identity when escape conditions are satisfied. State entries for other regions remain. Any open tail must be proved free of the local region before it can escape.

Updates through `mut` use the root-grant accounting of [§14.3](04-captures-and-access.md#143-mut): the root call admits `state<@r>`, and callees operate under the supplied grant's authority. The region entry remains in the enclosing computation until region elimination. Aliasable-state operations such as `Ref` operations declare their state effects in the ordinary way; `mut` authority does not discharge those effects.

### 27.4 Non-escape

A value may leave `region r { body }` only if all of the following hold:

- the result type does not mention `@r`;
- the result's capture/provenance summary does not retain `@r`;
- no outstanding task handle, first-class package, or live child owned by an enclosing taskgroup retains `@r`;
- no foreign/runtime object registered outside the region retains unsafe access into the region;
- every linear/resource obligation tied to the region has been consumed, transferred to a valid outer owner by an explicitly permitted conversion, or cleaned up.

The compiler MUST reject attempts to hide `@r` inside a closure, dynamic trait package, container, or other first-class wrapper. A lexical handler frame may retain `@r` only while the region remains in scope; because the handler is not first-class, that frame itself cannot escape.

### 27.5 Encapsulation

If a region-local computation has type/effects conceptually:

```text
T ! {state<@r> | e}
```

and `@r` is absent from `e` and does not escape through `T`, captures, or obligations, the enclosing region expression has external effects `e`. Additional fixed `state<@r>` entries are discharged by the same region boundary under [§61.1](11-formal-semantics.md#611-region-elimination).

This permits local mutation while preserving a pure external interface.

### 27.6 Regions are not allocators

A source region denotes mutable-state identity and lifetime. It does not promise stack allocation, arena allocation, stable addresses, bump allocation, or a particular garbage-collection strategy.

The implementation may choose any representation preserving the semantics.

## 28. Mutable abstractions

The core semantics distinguishes mutable-owner and aliasable-cell categories. `DynArray<T,@r>` and `Ref<T,@r>` below are bundled standard-library realizations and canonical examples; their exact nominal identities are not additional core semantic mechanisms.

### 28.1 Two categories

Eldude separates:

1. non-duplicable mutable owners; and
2. aliasable mutable cells/handles.

These have different semantics and APIs.

### 28.2 Non-duplicable mutable owners

`DynArray<T,@r>` is the canonical standard example.

It is never `Dup`. Its discardability depends on whether abandoning its contained obligations is legal.

Direct in-place mutation requires `mut` access and `state<@r>`.

At an owned-root call, grant formation charges that state effect ([§14.3](04-captures-and-access.md#143-mut)). An API's explicit state row, as below, is also propagated on calls using a supplied grant.

```eldude
fn push<T, @r>(
    mut values: DynArray<T, @r>,
    value: T,
) ->{state<@r>} Unit;
```

The implementation may mutate in place because the source semantics establish exclusive access to the owner for the dynamic call.

### 28.3 Aliasable shared cells

`Ref<T,@r>` represents explicitly aliasable mutable identity.

It is available only when:

```eldude
T: CaptureFree + Discard
```

`Discard` ensures that region destruction and cell replacement cannot strand an undiscardable payload merely because multiple aliases exist.

`CaptureFree` establishes that every possible payload has no tracked captures or fixed scoped dependencies ([§§9.6](02-types-and-ownership.md#96-capture-free-types), [13.5](04-captures-and-access.md#135-retention-horizons)). This type-level condition is checked at construction and on every payload-replacing operation; an individual value's empty capture summary or a longer-lived scope does not suffice.

A `Ref<T,@r>` handle is `Dup + Discard` and may therefore be freely aliased within the region's lifetime. The handle retains `@r` and is not `CaptureFree`.

### 28.4 `Ref` operations

Representative operations are:

```eldude
fn new<T, @r>(value: T) ->{state<@r>} Ref<T, @r>
where T: CaptureFree + Discard;

fn get<T, @r>(cell: Ref<T, @r>) ->{state<@r>} T
where T: CaptureFree + Discard + Dup;

fn replace<T, @r>(
    cell: Ref<T, @r>,
    value: T,
) ->{state<@r>} T
where T: CaptureFree + Discard;

fn set<T, @r>(cell: Ref<T, @r>, value: T) ->{state<@r>} Unit
where T: CaptureFree + Discard;
```

`new` creates aliasable mutable identity in `@r` and therefore necessarily carries `state<@r>`; this also prevents local polymorphic generalization from manufacturing a polymorphic mutable cell. `replace` transfers ownership of the previous payload to the caller and installs the new value. `new`, `replace`, and `set` enforce the same `CaptureFree + Discard` payload-type bound. `get` additionally requires `Dup` to copy the payload while leaving the cell intact.

`set` discards the previous payload using `T: Discard`. Generic wrappers use these ordinary bounds without inferred lifetime preconditions.

There is no safe `Ref<File,@r>` when `File` is linear/non-discardable, nor `Ref<Ref<Int,@s>,@r>` for any ordering of `@r` and `@s`. Scoped mutable contents use non-duplicable owners and `mut` under [§28.2](#282-non-duplicable-mutable-owners).

### 28.5 `view` and aliasable state

A `view` grant to an object containing or exposing a `Ref` does not freeze the referenced cell. Mutation through the explicit aliasable-state API remains possible and is visible through `state<@r>`.

`view` protects ownership/consumption, not observational constness of independent mutable identities.

## B.6 Aliasable state

```eldude
region r {
    let cell: Ref<Int, @r> = Ref::new(0);

    cell.set(1);
    let x = cell.get();
    x
}
```

`Int: CaptureFree + Discard + Dup`, so it is permitted as a `Ref` payload and may be read by value.

## 29. Resource usage

### 29.1 Linear values

A linear value is non-`Dup` and non-`Discard`.

Every completed control-flow path must consume it exactly once by:

- transferring ownership to another valid owner;
- invoking a consuming operation whose contract discharges the obligation;
- placing it under a cleanup owner that will discharge it;
- returning it to a caller when the return type carries the obligation.

### 29.2 Affine values

An affine value is non-`Dup` but `Discard`.

It may be consumed at most once and may be abandoned without hidden effect.

### 29.3 Structural propagation

Usage is structural. A product, sum, collection, closure, handler, or task-related wrapper inherits non-duplicability and non-discardability from contained obligations unless its abstraction explicitly transforms those obligations by a sound protocol.

### 29.4 COW and uniqueness

Copy-on-write is an implementation strategy, not a source qualifier.

For a `Dup` value, multiple semantic copies may share representation. For a non-`Dup` value, the implementation may exploit uniqueness/destructive reuse but MUST NOT expose another semantic owner merely because storage can technically be shared.

Eldude has no surface `unique` qualifier.

## 30. `Cleanup`

### 30.1 Intrinsic user-implementable trait

Eldude defines one compiler-recognized cleanup protocol, conceptually:

```eldude
intrinsic trait Cleanup<!e> {
    fn cleanup(self) ->{| e} Unit;
}
```

`Cleanup` uses ordinary coherent `impl` syntax but has compiler-enforced semantic restrictions.

### 30.2 Eligibility

Only non-`Dup` nominal types may implement `Cleanup`.

This avoids the incoherent situation in which a freely duplicable semantic value also has one canonical ownership-discharging cleanup action.

### 30.3 Canonical implementation

For a nominal type, there is at most one coherent cleanup implementation schema. The effect-row parameter describes effects of that canonical cleanup; it is not a mechanism for choosing alternative cleanup behaviors.

### 30.4 Cleanup method contract

`cleanup`:

- consumes `self`;
- returns exactly `Unit`;
- may perform declared effects;
- may contain `suspend`;
- may contain `diverge`;
- cannot return a recoverable `Result` as the cleanup protocol result.

A library requiring meaningful fallible completion exposes an explicit consuming operation such as:

```eldude
writer.finish()?
transaction.commit()?
```

Cleanup is fallback discharge, not the place to report a business-level completion result.

### 30.5 Control effects during cleanup

Cleanup is discharge-only structural control. Entering canonical cleanup establishes the cleanup cancellation mask in the ordinary structural context `Control`, and the cleanup body is checked by the same context-relative continuation-control envelope of [§17.3](05-effects-and-failure.md#173-derived-continuation-control-envelope) as any other computation.

Under that mask, `suspend` contributes no cancellation-abandonment edge because pending cooperative cancellation is not delivered into the cleanup action. The mask does **not** neutralize algebraic abandonment: an escaping family containing `affine` remains abandoning and MUST be handled before leaving the cleanup invocation. `tail` and `once` operations obey their ordinary resumption and handler-frame rules.

A cleanup defect follows the general structural-discharge precedence rules in [§20.2](05-effects-and-failure.md#202-defect-semantics). Cleanup divergence may prevent the prior structural outcome and later cleanup from being reached.

The `Cleanup<!e>` protocol guarantees that `mayAbandon(CleanupControl, e)` is false in its canonical masked execution context. Generic code using the protocol may rely on that guarantee without a new `cleanup-safe` predicate or a second effect classification.

## 31. `using`

### 31.1 Cleanup ownership

`using` establishes explicit structured cleanup ownership:

```eldude
using (file = open(path)?) {
    process(view file)
}
```

The acquired value must provide the canonical `Cleanup` protocol required by the construct.

`using` takes responsibility for any still-live binding it owns at scope exit.

### 31.2 Multiple acquisitions

```eldude
using (
    input = openInput(path)?,
    output = createOutput(path)?,
) {
    copy(view input, mut output)?
}
```

Acquisition occurs left-to-right. Cleanup of still-live resources occurs right-to-left.

If a later acquisition fails, already-acquired resources are cleaned before propagation.

### 31.3 Explicit early discharge

A resource under `using` may be explicitly consumed by a valid operation inside the body. When ownership has been fully discharged or transferred into another valid local owner, that original binding no longer requires cleanup at scope exit.

A `using`-owned resource may not be moved out of the `using` scope as an escaping ownership obligation. If outward ownership transfer is intended, the resource should not be placed under that cleanup scope or must be converted through an API whose result no longer retains the scoped cleanup obligation.

### 31.4 Exit behavior

For each still-live cleanup-owned binding, cleanup is initiated on normal completion, every legal continuing structural exit of [§62.2](11-formal-semantics.md#622-non-local-exit-judgment) crossing the scope, and nonrecoverable defect unwinding under [§20](05-effects-and-failure.md#20-defects-and-assertions). This includes affine continuation abandonment; it is the same exit judgment, not a second cleanup-specific escape rule.

### 31.5 Cancellation protection

Once cleanup for a structural exit begins, cooperative cancellation is masked until the cleanup action returns or diverges.

If cleanup suspends, sibling strands may run, but pending cancellation is not delivered into that cleanup action.

After cleanup completes, pending cancellation continues outward.

### 31.6 Cleanup effects

Cleanup effects are ordinary effects at the lexical point of cleanup execution, subject to the discharge-only restriction in [§30.5](#305-control-effects-during-cleanup). An enclosing handler may interpret resumable cleanup effects; affine zero-resumption control may not escape the cleanup invocation even when an outer handler for that family exists.

Handler nesting therefore determines interpretation:

```eldude
handle {
    using (file = open(path)?) {
        ...
    }
} with handler Fs {
    ...
}
```

allows the enclosing handler to interpret cleanup operations, while:

```eldude
using (file = open(path)?) {
    handle {
        ...
    } with handler Fs {
        ...
    }
}
```

performs cleanup after the inner handler has ended.

There is no privileged cleanup handler stack.

### 31.7 No cleanup on discard

Discarding an affine value never invokes `Cleanup` automatically.

A type for which silent abandonment would violate semantics must be linear rather than relying on hidden destruction.

## B.9 Explicit cleanup

```eldude
fn copyFile(src: Path, dst: Path)
    ->{fs, suspend, diverge} Result<IOError, Unit>
{
    using (
        input = openInput(src)?,
        output = openOutput(dst)?,
    ) {
        copy(view input, mut output)?;
        output.finish()?;
        Result::Ok(())
    }
}
```

The explicit `finish` reports meaningful failure. Any still-live cleanup-owned resource is discharged by `using` during scope exit.

---

[Specification index](../language-specification.md) · Previous: [6. Handlers and resumption](06-handlers.md) · Next: [8. Collections and iteration](08-collections.md)
