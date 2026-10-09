# Chapter 2 — Types and ownership

[Specification index](../language-specification.md) · Previous: [1. Foundations and programs](01-foundations.md) · Next: [3. Traits and dynamic abstraction](03-traits.md)

This chapter defines primitive and nominal data, polymorphism, and the permissions that determine how values may be used.

**Prerequisites:** [1. Foundations and programs](01-foundations.md).

The numbered rules are normative under the [specification conventions](../language-specification.md). Examples are illustrative snippets; names and omitted bodies may stand for surrounding program or library context.

A nominal type gives its fields one named data shape:

```eldude
struct Label {
    text: Text,
}
```

## In this chapter

- [6. Primitive types and kinds](#6-primitive-types-and-kinds)
- [7. Polymorphism and compile-time naturals](#7-polymorphism-and-compile-time-naturals)
- [8. Nominal algebraic data and patterns](#8-nominal-algebraic-data-and-patterns)
- [9. Usage and intrinsic permissions](#9-usage-and-intrinsic-permissions)

## 6. Primitive types and kinds

### 6.1 Primitive families

Required primitive families include:

```text
Bool Char Text Bytes Unit Never Nat
Int8 Int16 Int32 Int64 Int128
UInt8 UInt16 UInt32 UInt64 UInt128
Int UInt
Float32 Float64
```

`Nat` is an arbitrary-precision non-negative integer. `Never` is uninhabited. Null is not a value.

All primitive types satisfy `Dup + Discard + CaptureFree` ([§9.6](#96-capture-free-types)). `Int` is an alias of `Int64`, `UInt` of `UInt64`, and `Byte` of `UInt8`, on every target. For width `w`, `Intw` has range `[-2^(w-1), 2^(w-1)-1]` and `UIntw` has range `[0, 2^w-1]`. Native pointer widths do not alter these aliases. `Char` is one Unicode scalar value (U+0000–U+10FFFF excluding surrogates); `Bool` has exactly `false` and `true`.

Integer overflow is never undefined behavior. Ordinary arithmetic is checked as specified below; wrapping, saturating, widening, and recoverable checked-result operations are separate explicit APIs.

Decimal arithmetic and decimal literal policy remain deferred.

### 6.1.1 Primitive operator typing and evaluation

Ordinary binary arithmetic requires operands of the same numeric type after literal inference; there are no implicit numeric promotions. Operators on already typed values never insert a conversion. Unary `+` preserves a numeric value; unary `-` is available for signed integers and floats, and is rejected for `UIntw` and `Nat`. Binary operand evaluation is left-to-right, exactly once, before the primitive operation. All operators below have an empty effect row; specified arithmetic defects follow [§20](05-effects-and-failure.md#20-defects-and-assertions) rather than producing an exception, `Result`, or `diverge`.

| Operands | Operators | Result and behavior |
|---|---|---|
| Same `Intw`/`UIntw` | `+`, `-`, `*` | Same type; compute the mathematical result and defect if outside its range |
| Same `Nat` | `+`, `*` | Exact arbitrary-precision `Nat` |
| Same `Nat` | `-` | Exact `Nat`, or defect for a negative result |
| Same integer type or `Nat` | `/`, `%` | Same type; quotient truncates toward zero, remainder satisfies `a = q*b + rem` and has the dividend's sign or is zero |
| Signed integer | unary `-` | Same type; defect when negating the minimum value |
| Same float type | `+`, `-`, `*`, `/`, unary `-` | Same type; [§6.1.2](#612-floating-point-values-and-arithmetic) |
| Same numeric type | `==`, `!=`, `<`, `<=`, `>`, `>=` | `Bool`; mathematical integer order or [§6.1.2](#612-floating-point-values-and-arithmetic) float comparisons |
| Same `Char`, `Text`, or `Bytes` | `==`, `!=`, `<`, `<=`, `>`, `>=` | `Bool`; scalar-value order for `Char`, lexicographic scalar sequence order for `Text`, unsigned byte sequence order for `Bytes` |
| Same `Bool` or `Unit` | `==`, `!=` | `Bool`; equality of Boolean values, and all `Unit` values equal |

Integer division or remainder by zero defects. Signed `MIN / -1` defects because the quotient is unrepresentable; `MIN % -1` yields zero without overflowing. For unsigned integers and `Nat`, division is floor division because operands are nonnegative. Float `%`, Boolean ordering, arithmetic on text, and operators on user nominal types are rejected; explicit functions/trait methods provide those operations. `!=` is the Boolean complement of `==`. Each comparison precedence level is non-associative; mixed levels follow [§2.7](01-foundations.md#27-fixed-operators-and-precedence), while repeated comparisons at the same level require explicit separate computations. Logical negation uses the predefined pure function `not(Bool) -> Bool`; `!` remains algebraic dispatch.

The nonnumeric forms in [§2.7](01-foundations.md#27-fixed-operators-and-precedence) retain their own contracts: calls/member access ([§§4](01-foundations.md#4-functions-and-calls), [8](#8-nominal-algebraic-data-and-patterns), [10](03-traits.md#10-traits)), access-prefixed methods ([§14](04-captures-and-access.md#14-call-scoped-access)), turbofish ([§2.4](01-foundations.md#24-generic-syntax)), `?` ([§21.3](05-effects-and-failure.md#213-postfix-)), and optional access/coalescing ([§21.6](05-effects-and-failure.md#216-optional-access-and-coalescing)). `option ?? fallback` consumes one logical `Option` value, returns its owned `Some` payload or evaluates and returns `fallback` for `None`; ordinary `Dup` may preserve a bound source. Both alternatives obey the branch-join rules, and `fallback` must have the payload type. No fallback evaluation occurs for `Some`.

### 6.1.2 Floating-point values and arithmetic

`Float32` and `Float64` use IEEE 754 binary32 and binary64 value/encoding semantics. Ordinary arithmetic rounds each operation to its result format using round-to-nearest, ties-to-even; subnormals are supported with gradual underflow. Overflow produces signed infinity. Division by signed zero and invalid operations produce IEEE infinity or NaN as appropriate, without an Eldude arithmetic defect. Host floating-point trap enables, rounding modes, or flush-to-zero settings cannot alter these source semantics.

Every NaN produced by ordinary arithmetic, including unary negation of a NaN, is the canonical quiet NaN (`0x7fc00000` for binary32, `0x7ff8000000000000` for binary64). Explicit bit/FFI conversion APIs may represent other NaN encodings but must not expose hardware traps as ordinary operator behavior. For non-NaNs, negation reverses the sign including signed zero and infinity.

For any NaN operand, `==`, `<`, `<=`, `>`, and `>=` are false and `!=` is true. Positive and negative zero compare equal. Infinities compare in their mathematical order. NaNs therefore do not satisfy an equivalence relation or total ordering; explicit total-order APIs may define a separate contract. Optimization may not reassociate arithmetic, fuse multiply-add, or use excess intermediate precision when it changes these results.

### 6.1.3 Numeric literals and defaulting

Integer literals use decimal digits or `0b`, `0o`, `0x` prefixes with binary, octal, or hexadecimal digits. Decimal floating literals contain a decimal fraction and/or `e`/`E` exponent. Digits may be separated by a single underscore; leading, trailing, or repeated underscores within a numeric token are rejected. A fractional dot requires a digit afterward, so `1.field` remains member access. A sign is a prefix expression, not part of the token, except an exponent's sign.

An adjacent suffix fixes the type: `i8`, `i16`, `i32`, `i64`, `i128`, `u8`, `u16`, `u32`, `u64`, `u128`, `int`, `uint`, `nat`, `f32`, or `f64`. A decimal integer-shaped literal with a float suffix is permitted; hexadecimal/binary/octal forms do not take float suffixes. A fractional/exponent literal cannot have an integer suffix. Suffix names are not reserved identifiers outside numeric tokens.

Unsuffixed integer literals use an expected numeric type when one is fixed by the surrounding annotation, parameter/result contract, or another typed operand; otherwise they default to `Int`. Unsuffixed fractional/exponent literals use an expected float type or default to `Float64`. In an otherwise unconstrained arithmetic expression containing both integer-shaped and float-shaped literals, use `Float64` for the whole same-type operand group; an all-integer literal group defaults to `Int`. Conflicting fixed types are rejected rather than promoted. Defaulting never retries a wider type to make an out-of-range literal legal.

Integer literals are checked against the chosen range at compile time. Direct unary `-` on an integer literal, allowing parentheses around that literal, is checked as one signed mathematical literal, so the minimum signed value is expressible; applying negation to an already typed minimum value still defects. Float literals are converted directly from their exact mathematical value to the selected binary format with ties-to-even rounding; a finite literal rounding to infinity is rejected. Rounding to a subnormal or signed zero is allowed. Integer-shaped literals expected as floats use that same conversion without a prior integer-width truncation.

Thus `127i8` is valid, `128i8` is rejected, `-128i8` is valid, `1 + 2.0` defaults to `Float64`, and an unconstrained integer beyond `Int64` is rejected unless annotated/suffixed with a suitable type such as `Nat`. Floating infinities and NaNs are supplied by explicit primitive/library values rather than special literal keywords.

### 6.2 Kinds

The static semantics distinguishes at least:

```text
Type
Effect
EffectRow
Region
CaptureRow
NatIndex
Constraint
```

and constructor kinds such as:

```text
Type -> Type
(Type -> Type) -> Constraint
EffectRow -> Constraint
```

The compiler defines intrinsic constraints over non-type semantic categories when they expose an already-derived property rather than a user-defined protocol. This includes `NonAbandoning : EffectRow -> Constraint`, defined normatively in [§17.3](05-effects-and-failure.md#173-derived-continuation-control-envelope). It is not a trait and cannot be implemented by user code.

### 6.3 Generic parameter categories

Declarations visually distinguish non-type categories:

```eldude
<T, F<_>, @r, !e, ..C, #N>
```

meaning:

```text
T      type parameter
F<_>   unary type-constructor parameter
@r     region parameter
!e     effect-row parameter
..C    capture-row parameter
#N     compile-time natural parameter
```

Within a syntactic context that already establishes the category, the bare variable is used:

```eldude
fn apply<A, B, !e>(f: fn(A) ->{| e} B, value: A) ->{| e} B;
```

Region identities remain written `@r` at use sites.

## 7. Polymorphism and compile-time naturals

### 7.1 Parametric polymorphism and local generalization

Local rank-1 polymorphism may be inferred, but local generalization is governed by a conservative normative rule rather than compiler discretion. For a binding conceptually:

```eldude
let name = initializer;
```

the compiler first checks `initializer` monomorphically, obtaining a type `T`, effect row `e`, and result capture/provenance summary `C`. Implicit generalization is permitted only when all of the following hold:

1. `e` is the empty effect row. Evaluation that performs `state<@r>`, foreign/host behavior, suspension, algebraic effects, or any other admitted effect is therefore not implicitly generalized.
2. Every variable selected for generalization is not free in the surrounding typing environment, region/provenance environment, usage environment, active-access environment, structural-control context, or `C`. Generalization cannot detach a variable from an existing owner/provenance obligation.
3. Lexical region identities and other generative provenance identities are never implicitly generalized.
4. An explicit local `forall` annotation may request polymorphism but MUST satisfy the same formation conditions; annotation cannot force generalization of an effectful or identity-producing initializer.

When these conditions do not hold, the binding is monomorphic. This is an effect-based value restriction: ordinary pure values and pure closure construction still generalize, while mutable-identity creation does not.

For example:

```eldude
let identity = fn(x) => x;
```

is generalizable. By contrast, construction of an aliasable cell has `state<@r>` and is monomorphic at that binding:

```eldude
region r {
    let cell = Ref::new(fn(x) => x);
    // `cell` is not generalized to forall<A>. Ref<fn(A) -> A,@r>.
}
```

Higher-rank values require explicit annotation where inference would be ambiguous.

```eldude
let id: forall<T>. fn(T) -> T = fn(x) => x;
```

### 7.2 Higher-kinded parameters

Constructor parameters state arity:

```eldude
F<_>
F<_, _>
```

Eldude supports named higher-kinded parameters but not surface type-level lambdas.

### 7.3 Compile-time naturals

Compile-time natural parameters are declared with `#`:

```eldude
fn reverse<T, #N>(values: Array<T, N>) -> Array<T, N>;
```

`N` in `Array<T,N>` is a compile-time index, not a runtime integer.

The natural-expression fragment consists of unsuffixed nonnegative integer literals, index parameters, parentheses, addition, and multiplication. Equality normalizes to a polynomial with nonnegative arbitrary-precision coefficients and monomials ordered by canonical parameter identity. This algorithm terminates; it does not solve equations backwards for unknown indices. Other arithmetic in a type index is rejected. Arbitrary user runtime functions are never evaluated to establish type equality.

## 8. Nominal algebraic data and patterns

### 8.1 Products

Nominal products use `struct`:

```eldude
struct User {
    name: Text,
    age: UInt,
}
```

Construction supports field shorthand:

```eldude
User { name, age }
```

Eldude currently has no structural records or record-update syntax.

Data-field projection `receiver.field` returns an ordinary value while preserving a bound receiver. It MUST require the selected field's type to satisfy `Dup`; the aggregate itself need not be `Dup`. Projection never moves a field out of a retained aggregate, creates a partially moved aggregate, or returns a reference/access-grant value. Field visibility and ordinary active-access checks still apply. Receiver-consuming method calls follow [§10.4](03-traits.md#104-method-lookup) instead.

An owned binding used as the receiver, including a parenthesized binding, remains owned and available after projection. An existing `view`/`mut` parameter may likewise provide non-consuming access for a duplicable field read. A computed owned temporary receiver MUST additionally satisfy `Discard`, because it is abandoned after the field copy; a non-discardable temporary must first be bound and its ownership explicitly discharged. The receiver is evaluated exactly once, and the copied field preserves its own tracked captures/provenance.

For example:

```eldude
struct Pair {
    file: File,
    label: Text,
}
```

Given an owned `pair: Pair` and a linear `File`, these are independent alternatives:

```eldude
let label = pair.label;             // valid: duplicates Text and preserves pair
let file = pair.file;               // invalid: File is not Dup
let Pair { file, label } = pair;    // transfers both fields and consumes pair
let Pair { file: _, label } = pair; // invalid: File is not Discard
```

The owned-pattern alternatives use [§8.4](#84-pattern-matching). Reading a non-`Dup` field without taking ownership uses an explicit scoped projection API ([§15](04-captures-and-access.md#15-scoped-access-projection)).

### 8.2 Sums

Nominal sums use `enum`:

```eldude
enum Option<T> {
    None,
    Some(T),
}
```

### 8.3 GADTs

GADTs may give constructors explicit result types:

```eldude
enum Expr<T> where {
    Literal: fn(Int) -> Expr<Int>,
    IsZero: fn(Expr<Int>) -> Expr<Bool>,
    Pair: forall<A, B>. fn(Expr<A>, Expr<B>) -> Expr<(A, B)>,
}
```

Constructor-local hidden variables are existentially packaged by the GADT constructor. No separate general existential syntax is required.

### 8.4 Pattern matching

`match` is exhaustive. `let` accepts only irrefutable patterns. Or-pattern alternatives bind the same names with compatible types and usage obligations.

GADT patterns may refine local type equalities.

An owned scrutinee is evaluated once using ordinary ownership semantics. Matching a non-`Dup` owned binding consumes that binding as a whole; a `Dup` scrutinee may be semantically duplicated so the original binding remains available. A constructor/product/tuple pattern decomposes the selected owned value and transfers its components to their subpatterns. An ordinary name pattern takes ownership of its matched value. Decomposition leaves no partially moved aggregate available for later use, and it is permitted only where the relevant representation/constructor is visible.

Every owned component must be accounted for by its subpattern. An owned wildcard `_` MUST require the matched value to satisfy `Discard`, including when the wildcard ignores a whole aggregate. Fields cannot be implicitly omitted to abandon their ownership obligations, and ignoring a value does not invoke cleanup. Nominal strengthening still applies to a wildcard on the nominal value itself; visible constructor decomposition is a consuming use of that value, after which its fields retain their own usage obligations.

Constructor tests, alternative selection, and guard evaluation MUST NOT move components out of the scrutinee before an arm is selected. During a guard, a non-`Dup` pattern-bound name provides only projected `view` access to its component, not an owned binding; `Dup` components may be copied. These inspection grants cannot be captured, returned, or used for mutation and end when guard evaluation ends. Ownership is transferred to the selected arm only after its guard succeeds. A rejected alternative or false guard leaves the scrutinee intact for subsequent alternatives.

Matching through an existing `view`/`mut` grant is non-consuming inspection, not owned decomposition. Ordinary value bindings produced by such a pattern require their matched types to satisfy `Dup`; a non-`Dup` component is inspected through scoped projection rather than bound as a new owner. Ignoring a component in such inspection does not require `Discard`, because ownership remains with the caller. Matching does not reify or transfer the grant.

### 8.5 Finite inductive recursive declarations

Source recursive nominal data is restricted to finite inductive declarations. Build the nominal dependency graph after expanding transparent aliases and constructor-local GADT equalities; each occurrence of a nominal identity in a representation creates a dependency. Each strongly connected component is one recursive declaration group. Every occurrence of a group member in the group's stored fields/payloads MUST be fully applied and occur only beneath tuple/product/sum storage and nominal constructor argument positions certified as finite and strictly positive.

For this finite fragment, an occurrence beneath any function type (including its result), raw pointer, aliasable mutable identity, associated projection, or constructor parameter with unknown storage behavior is not a finite strictly positive occurrence and is rejected. Recursive occurrences in GADT constraints or result indices are also rejected; the constructor's outer result must be the declared enum, while indices not mentioning the recursive group may vary as in [§8.3](#83-gadts). This is a conservative storage-based positivity rule, not a variance assumption inferred from a callable's effect row.

A nominal constructor's finite positive parameter profile is derived from its representation: a parameter qualifies only when every occurrence is in the storage positions above. Phantom parameters qualify but introduce no stored subvalue. For a GADT, a parameter profile is certified only when every constructor result uses the enum's indices uniformly as distinct corresponding parameter variables and constructor equalities have been propagated into payload types. If any constructor computes or refines those indices, no parameter positions are certified; the GADT may still be inductive through its direct recursive payloads. An index is not presumed phantom merely because it is absent under its source name from a payload. For mutually recursive declarations, begin with all candidate positions and repeatedly remove positions failing the rule until a fixed point; then check recursive group occurrences against the resulting profiles. Primitive identities and opaque runtime/foreign abstractions have compiler/audited profiles, defaulting to no certified storage positions. Unknown higher-kinded parameters have no such profile. The derived profile is canonical interface data when clients need it to check a recursive declaration; opacity does not permit clients to assume positivity.

Recursive transparent type aliases are rejected rather than introducing equi-recursive types. Nonrecursive nominal data may contain ordinary function values and mutable identities. Its existence does not make those values finite inductive subterms. A recursive group's runtime values consist of finitely many stored constructor nodes; safe construction cannot tie a cyclic stored-value knot. Foreign identities or mutable graphs may represent cycles through their own explicit abstractions, but traversing those identities does not use this inductive guarantee.

For example, `enum Chain<T> { End, Link(T, Chain<T>) }` is admitted. A recursive payload `fn(Bad) -> Int`, `fn() -> Bad`, `Ref<Bad,@r>`, or `F<Bad>` for an unconstrained constructor parameter is rejected. A visible finite nominal container may contain recursive children only in its certified storage positions.

## 9. Usage and intrinsic permissions

### 9.1 Fundamental predicates

Eldude recognizes two compiler-governed usage predicates:

```text
Dup       may semantically duplicate
Discard   may discard without consuming
```

They are written with ordinary constraint syntax:

```eldude
where T: Dup
where T: Discard
where T: Dup + Discard
```

`Dup` and `Discard` are not user-implementable traits. An `impl Dup for T` declaration is invalid.

### 9.2 Usage classes

The two permissions induce three principal usage classes:

```text
                Dup   Discard
unrestricted    yes   yes
affine           no   yes
linear           no    no
```

Usage propagates structurally.

A composite containing a non-discardable obligation is non-discardable. A composite containing a non-duplicable obligation is non-duplicable.

### 9.3 Resource-root strengthening

A nominal declaration may deliberately strengthen usage:

```eldude
linear struct File;
affine struct CancelToken;
```

Structural derivation establishes the maximum usage permissions justified by representation. Nominal strengthening may only remove permissions from that maximum; it never grants a permission forbidden by a field or contained obligation.

A declaration may not weaken a stronger obligation implied by its fields.

Containing types do not repeat usage modifiers already implied structurally.

### 9.4 No hidden effect on discard

`Discard` means exactly that abandoning the value does not itself perform a semantic effect.

Discarding a value MUST NOT implicitly:

- run user cleanup;
- cancel a task;
- perform I/O;
- invoke an effect handler;
- execute arbitrary user code.

This law is central to cleanup and concurrency.

### 9.5 Mutable-owner status

Formation of a root `mut` access grant depends on a compiler-recognized mutable-owner judgment distinct from `Dup`/`Discard`. Conceptually:

```text
MutableOwner<T, @r>
```

means that `T` denotes a non-duplicable owner of mutable identity in region `@r` whose in-place operations are governed by `state<@r>`. `T: not Dup` is necessary but not sufficient: a linear resource such as `File` does not acquire mutable-owner identity merely because it is non-duplicable.

Mutable-owner status is not a user-implementable trait and does not participate in trait resolution. It is an intrinsic semantic fact of designated nominal state abstractions and is exported in canonical interfaces when clients need to form root `mut` grants. `DynArray<T,@r>` is the canonical standard example. Scoped projection ([§15](04-captures-and-access.md#15-scoped-access-projection)) may derive a `mut T` grant to an arbitrary subvalue from an already active parent-owner grant; the derived grant retains the parent owner identity/projection path and does not require `T` itself to satisfy `MutableOwner`. The core does not define a general user-extensible mechanism for minting new root mutable-owner identities; abstractions that require new identity mechanisms are built from existing state primitives or audited unsafe/runtime facilities until such a mechanism is independently justified.

Root-grant formation accounts for `state<@r>` under [§14.3](04-captures-and-access.md#143-mut). The grant carries that accounted state authority through forwarding and projection; the target type of a projected grant need not name the parent region.

### 9.6 Capture-free types

`CaptureFree : Type -> Constraint` is a compiler-derived structural property. `T: CaptureFree` guarantees that every value of `T` has no tracked captures or fixed scoped dependencies under [§13](04-captures-and-access.md#13-captures). It is not a user-implementable trait, a usage permission, or a relative lifetime/outlives constraint.

Generic code uses ordinary constraint syntax:

```eldude
where T: CaptureFree
where T: CaptureFree + Discard
```

The compiler derives the property from complete structural types or published compiler-derived/audited profiles. Ordinary scalars and immutable tuples, records, enums, and collections qualify when all their possible stored contents are `CaptureFree` and they have no additional hidden provenance or ownership obligations. All enum alternatives must satisfy the rule. A function type must establish that its permitted environments have no tracked captures and that its complete contract has no fixed scoped dependencies.

A generic type parameter needs the bound or sufficient evidence after instantiation. An opaque type, unknown container, or erased package needs published evidence sufficient to establish the property for every value of its type; opacity alone supplies none. An empty container or one value's empty capture summary does not establish `CaptureFree` for a type that can also hold scoped values.

Scoped references, task handles, and closures retaining scoped state do not satisfy `CaptureFree`. In particular, `Ref<Int,@r>` is `Dup + Discard` but retains `@r`, so those permissions do not imply `CaptureFree`. `CaptureFree` grants neither usage permission; APIs such as aliasable cells require `Discard` separately.

---

[Specification index](../language-specification.md) · Previous: [1. Foundations and programs](01-foundations.md) · Next: [3. Traits and dynamic abstraction](03-traits.md)
