# Chapter 8 — Collections and iteration

[Specification index](../language-specification.md) · Previous: [7. Regions, mutable state, and cleanup](07-state-and-cleanup.md) · Next: [9. Structured concurrency](09-concurrency.md)

This chapter applies ownership, scoped access, and termination rules to collection APIs and iteration.

**Prerequisites:** [2. Types and ownership](02-types-and-ownership.md), [4. Closures, captures, and scoped access](04-captures-and-access.md), [5. Effects, termination, and failure](05-effects-and-failure.md), [7. Regions, mutable state, and cleanup](07-state-and-cleanup.md).

The numbered rules are normative under the [specification conventions](../language-specification.md). Examples are illustrative snippets; names and omitted bodies may stand for surrounding program or library context.

This chapter specifies the language/library contracts used by collections, `for`, and scoped projection. Concrete collection families, representations, and cost guarantees belong to the bundled [standard-library profile](../standard-library.md). They do not introduce independent language mechanisms.

## B.7 Non-`Dup` collection inspection

```eldude
view values.with(index, fn(view item) {
    inspect(view item)
});
```

No reference value escapes the callback.

## In this chapter

- [32. Standard sequence abstractions](#32-standard-sequence-abstractions)
- [33. Collection usage](#33-collection-usage)
- [34. Indexing and scoped inspection](#34-indexing-and-scoped-inspection)
- [35. Iteration](#35-iteration)
- [36. Maps, sets, text, and numeric policy](#36-maps-sets-text-and-numeric-policy)
- [37. Laziness policy](#37-laziness-policy)

## 32. Standard sequence abstractions

### 32.1 `List<T>` (standard library)

Under the bundled standard-library profile, list literals construct the finite immutable sequence `List<T>`:

```eldude
[1, 2, 3]
```

### 32.2 `TreeList<T>` (standard library)

`TreeList<T>` follows the same structural ownership laws as `List<T>`; its persistent representation and cost contract are library policy.

### 32.3 `LinkedList<T>` (standard library)

`LinkedList<T>` is an ordinary finite inductive cons structure subject to [§8.5](02-types-and-ownership.md#85-finite-inductive-recursive-declarations). Its constructors and operations are defined by the library profile.

### 32.4 `Array<T,N>` (standard library)

`Array<T,N>` is immutable statically sized storage. `N` is a `NatIndex`.

```eldude
Array<Byte, 32>
```

Under the bundled profile, list literals do not contextually become arrays.

The initial library API preserves its fixed shape.

### 32.5 `DynArray<T,@r>` (standard library mutable-owner example)

`DynArray<T,@r>` is mutable storage owned in region `@r`.

It is never `Dup`. Direct mutation requires `mut` plus the region-state accounting specified in [§14.3](04-captures-and-access.md#143-mut); its API's explicitly declared state effects remain admitted on forwarded calls.

Freezing consumes the mutable owner and produces an immutable value representation. The implementation may transfer/reuse the allocation when legal.

## 33. Collection usage

### 33.1 Structural element propagation

Collection usage derives from `T`.

Conceptually:

```text
T unrestricted  -> List<T> unrestricted
T affine        -> List<T> affine
T linear        -> List<T> linear
```

The same structural principle applies to `Array`, `TreeList`, `LinkedList`, and appropriate owning views.

### 33.2 Permission-specific operations

An operation that preserves the original collection and returns an element by value requires:

```text
T: Dup
```

An operation that discards an element requires:

```text
T: Discard
```

A consuming operation may work for arbitrary `T` when it transfers every element/obligation exactly once. If such an operation can fail recoverably after consuming an input that is not known `Discard`, every failure variant must return that ownership obligation, discharge it structurally, or the operation must instead require `Discard`.

Representative contracts:

```eldude
fn get<T>(view values: List<T>, index: Int) -> Option<T>
where T: Dup;

fn remove<T>(
    values: List<T>,
    index: Int,
) -> Result<(BoundsError, List<T>), (T, List<T>)>;

fn filter<T, ..C>(
    values: List<T>,
    predicate: fn(view T) -> Bool captures {..C},
) -> List<T>
where T: Discard,
      ..C: Dup + Discard;

fn partition<T, ..C>(
    values: List<T>,
    predicate: fn(view T) -> Bool captures {..C},
) -> (List<T>, List<T>)
where ..C: Dup + Discard;
```

`filter` may discard rejected values, so `T: Discard`. `partition` preserves all elements, so it requires no element discardability.

### 33.3 Replacement

An immutable update that discards a displaced element requires `T: Discard`:

```eldude
fn set<T>(values: List<T>, index: Int, value: T) -> Result<BoundsError, List<T>>
where T: Discard;
```

A replacement API can instead return the displaced value and avoid that requirement. Its failure path must also return both consumed inputs when they are not known discardable:

```eldude
fn replace<T>(
    values: List<T>,
    index: Int,
    value: T,
) -> Result<(BoundsError, List<T>, T), (T, List<T>)>;
```

## 34. Indexing and scoped inspection

### 34.1 Value-returning indexing

Ordinary indexing returns a value only when duplication is semantically legal.

Static-bound syntax such as:

```eldude
array[i]
```

may be permitted when bounds are established by the static context and `T: Dup`.

Dynamic checked access uses APIs such as `get` and likewise requires `T: Dup` when the collection remains available afterward.

### 34.2 Non-`Dup` inspection

For non-duplicable elements, non-consuming inspection uses scoped access projection:

```eldude
view values.with(index, fn(view item) {
    inspect(view item)
});
```

No borrowed element value is returned.

### 34.3 Ownership extraction

Ownership extraction from a dynamic sequence consumes the source and returns both the extracted element and the remainder, or otherwise preserves every obligation through a collection-specific consuming API.

For `Array<T,N>`, fixed shape is preserved by default. Shape-changing removal may be added later as an explicit O(N) consuming conversion to `Array<T,N-1>` if concrete use cases justify it; it is not required by the initial specification.

### 34.4 Owning immutable subviews

An owning immutable view type such as `SharedSlice<T>` MAY exist for values whose element semantics permit retained sharing. Such a type MUST state its ownership and usage constraints explicitly; it is not a general borrowed view into mutable storage.

A standard `SharedSlice<T>` SHOULD require at least `T: Dup + Discard` if its handles themselves are unrestricted and overlapping.

## B.8 Ownership-preserving removal

```eldude
match files.remove(index) {
    case Result::Ok((file, rest)) => {
        use(file);
        use(rest);
    };
    case Result::Err((error, original)) => {
        report(error);
        use(original);
    };
}
```

A linear element is transferred on success; on bounds failure the original linear collection is returned rather than silently discarded.

## 35. Iteration

### 35.1 Ownership-threaded iterator protocol

The bundled standard-library iterator protocol used by `for` is conceptually:

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

Each call consumes the current iterator state and returns either completion or one item plus the next iterator state.

There is no required mutable borrowed iterator object.

### 35.2 Iterator usage

The iterator's usage class reflects the remaining collection obligations.

For a linear source, the iterator is linear. Each `next` transfers exactly one item plus the remaining iterator state.

Partially consuming such an iterator does not make the remaining elements disappear.

### 35.3 `for`

`for` consumes an iteration state according to this protocol.

For an unrestricted source, ordinary `Dup` semantics permit the source value to remain available by semantic duplication. For a non-`Dup` source, iteration consumes it.

An early `break`, `return`, `?`, affine zero-resumption effect, or cancellation crossing a loop with a live iterator remainder is legal only when the remaining iterator state can be legally discharged by the ordinary control-exit rules. A nonrecoverable defect is not statically checked as such an exit; structural owners still unwind, but a naked iterator remainder is not guaranteed to be consumed on a defect path.

Therefore a recoverable/continuing exit from a loop over a linear iterator cannot silently abandon its unconsumed tail.

### 35.4 Dynamic incompatibility of `Iterator`

Because `Iterator::next` returns `Self`, the standard static `Iterator` trait is not dynamically compatible with `any Iterator` under Eldude's `any` rules.

A runtime-erased streaming/source abstraction, if needed, must be a separately designed dyn-compatible trait rather than weakening the static iterator protocol.

### 35.5 Finite iteration and non-divergence

The iterator protocol alone does not prove finiteness.

`for` may omit `diverge` only with certified finite completion and non-diverging source evaluation, steps, body, and structural discharge ([§19.5](05-effects-and-failure.md#195-for)). Potentially unbounded iteration contributes `diverge`.

Finite completion is recorded as `finite-iteration = true` on the selected concrete `Iterator` implementation in its canonical interface ([§72.7](12-interfaces-and-tooling.md#727-human-readable-semantic-interface-rendering)). The ordinary compiler may derive this fact when `next` is non-diverging and every reachable `Next::Item` returns a successor iterator that is a strict finite stored subterm of its input under [§19.2](05-effects-and-failure.md#192-structural-recursion). Bundled runtime primitives such as the `List` iterator may instead provide an audited finite-length-decrease contract. Without this fact, iteration is conservatively unbounded. Storage positivity alone is insufficient: an implementation returning its unchanged input forever has finite stored values but infinite iteration. The fact is not a user-implementable predicate or an unchecked source annotation.

### 35.6 Ownership-preserving early-exit combinators

The ownership-threaded iterator protocol is intentionally strict about early exit. Standard collections and iterator adapters SHOULD therefore provide consuming combinators whose recoverable outcomes preserve every unconsumed obligation rather than forcing callers to manually reconstruct iterator state.

For example, a sequence search that supports arbitrary `T` may expose a result conceptually like:

```eldude
struct SplitFound<T> {
    before: List<T>,
    item: T,
    after: List<T>,
}

enum FindSplit<T> {
    Found(SplitFound<T>),
    NotFound(List<T>),
}

fn findSplit<T, !e, ..C>(
    values: List<T>,
    predicate: fn(view T) ->{| e} Bool captures {..C},
) ->{| e} FindSplit<T>
where e: NonAbandoning,
      ..C: Dup + Discard;
```

All input elements remain represented on every recoverable outcome. Similar library families SHOULD cover split/search and fallible fold/traversal patterns. A consuming combinator that can return early while owning arbitrary non-`Discard` state MUST return that state, discharge it structurally, or impose the corresponding `Discard` requirement; this is the same general ownership-preserving failure law as [§33.2](#332-permission-specific-operations).

## 36. Maps, sets, text, and numeric policy

### 36.1 Maps and sets

`Map<K,V>` and `Set<T>` are ordinary immutable library types with explicit equality/hash/order policies.

Eldude currently has no dedicated map/set literal syntax.

### 36.2 Text and bytes

`Text` is Unicode text. `Bytes` is raw octets.

Text APIs distinguish UTF-8 bytes, Unicode scalar values, and grapheme-cluster-oriented operations rather than pretending integer indexing has one universal meaning.

`Text` does not silently convert to `char*` at the FFI boundary.

### 36.3 Numeric conversions

There is no general `as` conversion operator.

Conversions use typed APIs such as:

```eldude
UInt32::from(x)
Float64::from(x)
```

Representation casts remain unsafe operations when applicable.

## 37. Laziness policy

### 37.1 Strict default

Ordinary bindings and arguments are eager. Constructing a function value delays its body by ordinary function semantics.

### 37.2 Memoized lazy values

A standard `Lazy<T>` MAY provide memoized pure non-diverging computation when repeated observation of the memoized result is semantically legal. A reusable `Lazy<T>` therefore requires `T: Dup` and derives any additional usage obligation from its retained computation environment.

### 37.3 Effectful delayed work

Effectful or potentially divergent delayed work does not require a new language arrow. An ordinary function value:

```eldude
fn() ->{| e} T captures {...}
```

already expresses a delayed computation with explicit effects and capture/usage semantics.

---

[Specification index](../language-specification.md) · Previous: [7. Regions, mutable state, and cleanup](07-state-and-cleanup.md) · Next: [9. Structured concurrency](09-concurrency.md)
