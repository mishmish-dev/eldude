# Eldude Language Specification

**Version:** 0.0.2

**Status:** architectural consolidation; pre-implementation normative design

`MUST` and `MUST NOT` state normative requirements. `SHOULD` permits a documented alternative. `MAY` grants implementation freedom.

This document consolidates the current Eldude design after the 0.6 architectural audit. It is not a 1.0 declaration. The design remains subject to further adversarial composition audits before stabilization.

This specification is normative for both semantics and the source-level parsing contract. §2 defines lexical/operator rules and parsing conventions. The complete standalone grammar is [Eldude Formal Grammar](ELDUDE-FORMAL-GRAMMAR.md). Its normative artifact is [eldude.ebnf](eldude.ebnf); Appendix F and the standalone document are mechanically verified generated presentations, including a distinct canonical-interface entry point. [eldude-grammar.json](eldude-grammar.json) exports normalized BNF, lexical rules, and parsing conventions for machine consumption. Parsing MUST NOT require name resolution, type checking, trait resolution, or imported implementation bodies.

The specification is ordered by semantic dependency. Later mechanisms may rely on earlier ones; earlier mechanisms do not depend on later feature-specific rules.

## Reading order

```text
foundations and program model
    ↓
types, usage, traits, and abstraction
    ↓
functions, captures, and call-scoped access
    ↓
effects, non-divergence, failure, and handlers
    ↓
regions, mutable identity, and cleanup
    ↓
collections and iteration
    ↓
structured concurrency
    ↓
host, unsafe, and FFI boundary
    ↓
formal static/dynamic semantics
    ↓
separate compilation and tooling
```

# Part I — Foundations and Program Model

## 1. Semantic dimensions

Eldude is a strict, statically typed, non-diverging-by-default functional language with explicit effects, usage-sensitive values, algebraic handlers, lexical mutable regions, and structured concurrency.

Its principal semantic dimensions are distinct:

| Dimension | Meaning |
|---|---|
| Type | Data shape and invariant |
| Effect row | Computation behavior represented in the effect-row contract |
| Capture set | Retained resource, provenance, and lexical obligations of a first-class value |
| Region | Identity and lexical lifetime of mutable state |
| Usage | Permission to duplicate, discard, or require exact consumption |
| Handler | Interpretation of algebraic operations |
| Taskgroup | Lexical ownership of concurrent child strands |
| Host | External runtime implementation selected by an application |
| Unsafe boundary | Explicit assertion of proof obligations not established by safe Eldude |

These dimensions MUST NOT be implicitly collapsed into one another. In particular:

- an effect does not imply a capture;
- a capture does not imply an effect;
- region identity does not imply a physical allocator or address;
- usage does not imply physical uniqueness of representation;
- `unsafe` is not an effect;
- the host is not an ambient capability value.

Ordinary safe Eldude has no general safe reference type, no lifetime language, and no source-level shared-memory parallelism model.

## 2. Surface and parsing model

### 2.1 Blocks and delimiters

Eldude uses braces and semicolons. Indentation is formatting only.

```eldude
fn f(x: Int) -> Int {
    let y = x + 1;
    y * 2
}
```

A block's final unterminated expression is its result. An empty block has value `()` and type `Unit`.

### 2.2 Namespaces and qualification

`::` is used for module, type, effect, and associated-name qualification.

```eldude
collections::List
Option::Some
Console::print
```

The parser MUST NOT require name resolution to decide how tokens associate.

### 2.3 Operators

Operator spelling and precedence are fixed by the language. User-defined operators and user-defined precedence do not exist.

Operator parsing MUST NOT depend on imported modules or trait resolution.

### 2.4 Generic syntax

Type arguments use angle brackets. Explicit expression-level generic application uses turbofish.

```eldude
List<Text>
id::<Text>("hello")
```

### 2.5 Imports

Imports are explicit and grouped:

```eldude
import collections::{List, Map};
```

Aliases are explicit:

```eldude
import collections::{HashMap as Map};
```

Wildcard imports do not exist.

### 2.6 Reserved words, sigils, and longest-token rules

The source grammar reserves the following words because they participate directly in 0.0.2 syntax:

```text
affine any as assert await break captures case const continue decreases
effect else enum extern false fn for forall forward handle handler if impl
import in intrinsic let linear match module mut once pub region resume return self spawn
struct suspend taskgroup trait true try type unsafe using view where while
diverge
```

`with`, `tail`, and `state` are contextual words: they introduce handler composition, tail-resumption declarations, and region-state row entries in those specific grammatical positions, and are ordinary identifiers elsewhere. This permits projection APIs named `with`, record fields named `tail`, and values named `state` without name-dependent parsing.

`many`, `abort`, `error`, and `host` are not reserved words in 0.0.2. Many-shot resumption is deferred; abortive operations are expressed by `affine ... -> Never`; expected-error composition uses nominal enums; host selection is root/build metadata rather than source syntax. Primitive type names such as `Int`, `Bool`, and `Unit` are ordinary predefined type names rather than keywords.

The category sigils are context-free tokens:

```text
!e     effect-row generic parameter declaration
@r     region identity/reference
#N     compile-time-natural generic parameter declaration
..C    capture-row parameter/rest
```

At expression level, `!Qualified::op(...)` is algebraic operation dispatch. `!` is not an ordinary general-purpose prefix operator in 0.0.2. This prevents `!Console::check()` from having a second parse as boolean negation of an ordinary call.

Lexing uses longest-token matching for multi-character punctuation, including at least:

```text
::  ->  =>  .?  ??  ..  ==  !=  <=  >=
```

Turbofish is parsed as `::` followed by `<...>`; it is not a distinct semantic token. Nested generic closers are individual `>` tokens; 0.0.2 defines no `>>` shift operator.

### 2.7 Fixed operators and precedence

The following table is normative for parsing. It fixes association only; typing and evaluation behavior remain governed by the corresponding semantic/primitive contracts. Higher rows bind more tightly. User-defined operators and precedence do not exist.

| Level | Forms | Associativity / note |
|---|---|---|
| Postfix | call `(...)`, member `.name`, optional member `.?name`, indexing `[expr]`, turbofish `::<...>`, postfix `?` | left/postfix |
| Access-method call | `view receiver.method(...)`, `mut receiver.method(...)` | prefix applies to exactly the following method call |
| Numeric prefix | unary `+`, `-` | right; operand includes postfix operations |
| Multiplicative | `*`, `/`, `%` | left |
| Additive | `+`, `-` | left |
| Relational | `<`, `<=`, `>`, `>=` | non-associative |
| Equality | `==`, `!=` | non-associative |
| Coalescing | `??` | right |

`!Qualified::op(...)`, `await`, `spawn`, `unsafe { ... }`, `try { ... }`, `handle { ... } with handler ...`, `region name { ... }`, `using (...) { ... }`, and `taskgroup { ... }` are grammar-level expression forms rather than entries in the ordinary operator precedence ladder.

Angle brackets after a type path belong to the type grammar. Expression-level generic application requires turbofish, so parsing `a < b` never depends on discovering whether `a` names a generic function.

### 2.8 Core source grammar contract

The normative grammar is context-free. Appendix F reproduces the complete checked EBNF artifact. The following disambiguation rules are part of that contract:

- `value.method(args)` selects a consuming/value receiver (`self`);
- `view value.method(args)` selects `view self`;
- `mut value.method(args)` selects `mut self`;
- `view`/`mut` access arguments and access-prefixed method receivers apply to an in-scope binding (including a callback parameter carrying a projected grant), not to an arbitrary computed expression; compute an expression into a binding first when access must be granted to its result;
- this binding-only rule keeps `f(view x.method())` unambiguous: it is a plain argument whose expression is the `view self` method call, while `f(view x)` is an ordinary `view` argument;
- the parser chooses among the three method forms syntactically, before method lookup; the type checker later verifies that the selected method has the matching receiver mode;
- `!path::op(args)` is always algebraic operation dispatch;
- `@name`, `#name`, `!name` in generic-parameter lists, and `..name` in capture-row positions are determined solely by grammatical context;
- `semantic { ... }` is not ordinary source syntax; it belongs to the canonical-interface entry point of Appendix F;
- an unparenthesized nominal construction is excluded from the outer condition/scrutinee/source expression of `if`, `while`, `match`, and `for`; parentheses permit it and prevent confusion with the following block;
- `await` and `spawn` take the immediately following unary/postfix operand; use parentheses or a block to group a larger computation;
- an undelimited `=>` lambda body and the operand of `return` consume the longest following expression permitted by the enclosing grammatical delimiters. Among complete derivations, compare those body/operand end-token positions in order of their introducing `=>`/`return` tokens, earliest first, and choose the lexicographically greatest vector. Thus `fn(x) => x + 1` keeps the addition inside the lambda and `return f() + 1` returns the sum. Parenthesize the lambda/return expression when a following postfix/binary operation belongs outside it, as in `(fn(x) => x)(1)`;
- a capture clause attaches to the nearest unparenthesized function contract; parenthesize a returned function type before writing a capture clause for the outer function;
- a generic closing `>` immediately followed by `=` forms the longest token `>=`; separate them with whitespace when a closing delimiter and equality/initializer token are intended.

### 2.9 Lexical payloads and consolidated forms

Source is UTF-8. Identifiers use ASCII letters/underscore followed by ASCII letters/digits/underscores; capitalization does not create a second token category. Reserved words cannot be identifiers. `//` comments end at a newline or end of file; `/* ... */` comments are non-nesting. Whitespace/comments separate tokens except within literals. Numeric token forms are those of §6.1.3 and the artifact.

Double-quoted strings contain Unicode scalar values. Single-quoted character literals contain exactly one scalar value. Raw control characters U+0000–U+001F, unescaped delimiters/backslash, and literal newlines are excluded. Escapes are `\n`, `\r`, `\t`, `\0`, `\\`, `\"`, `\'`, and `\u{H}` with one to six hexadecimal digits representing a Unicode scalar value. Invalid scalar escapes are rejected. There are no raw, multiline, interpolated, or byte-string literal forms. String literals have type `Text`; character literals have type `Char`.

Anonymous function parameters may omit a type when ordinary inference or an expected function type supplies it, as in `fn(x) => x`. Named-function parameters are typed; receiver `self` uses its enclosing implementation/trait type. `forall<...>. Type` is the explicit higher-rank type form. An associated projection may use `T::Item` when its trait is unambiguous in the static contract, or `<T as Trait<Args>>::Item<GatArgs>` for explicit qualification. This is type syntax, not expression-level conversion.

Enum variants may use tuple payloads or nominal record payloads, for example `Cons { head: T, tail: LinkedList<T> }`; that record belongs to the enum constructor and is not a structural record type. Construction and patterns use `LinkedList::Cons { head, tail }`. All fields of an owned product/record pattern must be explicit, including wildcards; there is no rest pattern. Loop statements may omit a terminating semicolon; other nonfinal expressions require one.

## 3. Evaluation

### 3.1 Strict call-by-value

Eldude is strict and call-by-value.

For:

```eldude
f(a(), b())
```

execution evaluates:

1. `f`;
2. `a()`;
3. `b()`;
4. the call.

The implementation MAY optimize evaluation when it preserves all observable semantics, including effect order, defect order, divergence, suspension/interleaving, handler behavior, and ownership obligations.

### 3.2 Immutable bindings

`let` creates an immutable binding.

```eldude
let x = 10;
let x = x + 1;
```

The second binding shadows the first. Eldude has no assignment expression, assignment statement, compound assignment, or `let mut`.

An implementation MAY reuse storage destructively when the reuse is unobservable.

### 3.3 Conditions

Conditions and match guards require `Bool`. There is no truthiness.

### 3.4 Ordinary control flow

Eldude provides:

```text
if
match
for
while
break
continue
return
try
```

`break` has no result value in the current design; loops have type `Unit` unless another expression form explicitly provides a result. Branch ownership joins and loop header/back-edge/exit rules are normative in §§62.5–62.6.

Every non-local control exit that continues Eldude execution elsewhere is checked against usage, cleanup, capture, region, handler-continuation, and taskgroup obligations crossed by that exit. This includes `return`, `?`, loop exits, affine zero-resumption algebraic control, and cooperative cancellation. A nonrecoverable assertion defect is not such a recoverable exit; structural owners still perform specified defect unwinding, but ordinary naked linear obligations are not required to be discharged on a defect path.

## 4. Functions and calls

### 4.1 One function type syntax

Function types have fixed arity:

```eldude
fn(A) -> B
fn(A, B) -> C
fn(A) ->{fs} B
fn(A) ->{fs, diverge} B
```

There is no `A -> B` shorthand and no separate partial-function arrow.

### 4.2 Function syntax

Named function:

```eldude
fn add(x: Int, y: Int) -> Int {
    x + y
}
```

Anonymous function:

```eldude
fn(x: Int) => x * 2
```

or:

```eldude
fn(x: Int) -> Int {
    x * 2
}
```

No second lambda introducer exists.

### 4.3 Fixed arity and no implicit partial application

`add(1)` is an arity error when `add` expects two arguments.

Partial application uses an explicit closure:

```eldude
let addTwo = fn(x: Int) => add(2, x);
```

### 4.4 Positional parameters

Parameters and arguments are positional. Eldude currently has no labelled parameters, named call arguments, or default arguments.

APIs with many optional choices SHOULD use nominal option/configuration values.

## 5. Modules and top-level structure

### 5.1 One module per source file

Every source file declares exactly one logical module:

```eldude
module geometry::point;
```

Package/source resolution is build metadata, not part of import syntax.

### 5.2 Declaration-only top level

Top level contains declarations only. Importing a module does not execute arbitrary runtime code.

Every ordinary top-level `let` initializer MUST be pure and terminating, and its result type MUST satisfy `Dup + Discard`. This applies to private as well as exported bindings and is checked using the ordinary structural usage rules, including obligations retained by closures, opaque values, and erased packages.

A module binding is a reusable definition, not a globally tracked affine or linear owner. For example:

```eldude
linear struct Token;

let token = Token {};                 // invalid: Token is not Dup + Discard
let makeToken = fn() => Token {};     // valid: the capture-free factory is Dup + Discard
```

A factory may return a fresh ownership obligation on each invocation; the restriction concerns the value held by the top-level binding. Runtime startup and ownership of state/resources belong to the selected host/root lifecycle or explicit state abstractions created during runtime execution.

### 5.3 Exports and opacity

Visibility is module-based. Declarations are private to their defining module unless prefixed by `pub`. At module scope, `pub` is permitted on named functions, `let` bindings, nominal `struct`/`enum` declarations, type aliases, traits, and effects. It precedes other declaration modifiers: `pub linear struct File;`, `pub unsafe fn call(...);`. Local declarations cannot be `pub`. A module's `module path;` declaration names its logical identity and has no visibility modifier.

Fields, enum variants/GADT constructors, and inherent methods are separately private unless prefixed by `pub`. A public nominal type exposes its identity and canonical semantic guarantees, not its representation. For a struct literal or product pattern, the type and every field used in its complete construction/decomposition must be visible. A field read needs that field's visibility. A semicolon struct declaration has no externally visible construction/decomposition form; a public zero-field braced struct may expose its empty constructor. An enum constructor may be constructed or matched only when its variant is visible. Publishing a member of a private type does not export the type or make the member accessible outside its module.

```eldude
pub struct Point {
    pub x: Int,
    pub y: Int,
}

pub linear struct File; // public identity; hidden representation

pub enum Status {
    pub Ready,
    Internal,
}
```

A public trait's methods and associated declarations, and a public effect's operations, are all part of its visible contract; individual visibility modifiers there are invalid. Implementation methods inherit the trait method's visibility and cannot alter it. Implicit trait implementations have no `pub` modifier: their applicable headers are exported in the canonical index under §§10 and 72.4 even though their bodies remain private. Inherent methods use ordinary explicit `pub`.

An ordinary import creates private local names. `pub import path::{Name, Other as Alias};` additionally re-exports those names/aliases and is permitted only for already public entities. A re-export preserves the defining identity, ownership, and opacity; it does not reveal private members. Qualified lookup across a module boundary observes the same visibility rules as importing. No wildcard import or implicit re-export exists.

Every nominal/trait/effect identity appearing in a public author-visible contract must itself be publicly nameable, directly or through a public re-export. Private representation fields may contain private identities, provided canonical usage, positivity, captures, and other client-required guarantees are still exported without granting representation access. Public associated equations and method signatures cannot expose private nominal identities. Visibility never exempts the compiler from canonical interface completeness.

Exhaustiveness accounts for hidden enum variants using an opaque remainder. Outside the defining module, if any variants are hidden, a match requires a wildcard or name catch-all for that remainder; an owned wildcard still requires `Discard`, while a name transfers ownership (§8.4). Interfaces reveal that a hidden remainder exists without exporting its constructors. Eldude has no `some Trait` abstraction form.

### 5.4 Public contracts

Canonical exported contracts MUST contain every semantic fact required by clients: types, effects, effect-row constraints such as `NonAbandoning`, captures, usage guarantees, regions, generic naturals, trait requirements, handler residuals, cleanup facts, and relevant ABI/foreign semantic contracts. Application or embedding roots additionally carry the separate root-only host/embedding contract of §48.4.

Private implementation bodies are not part of ordinary downstream semantic checking.

# Part II — Types, Usage, and Abstraction

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

All primitive values have `Dup + Discard` and are capture-free. `Int` is an alias of `Int64`, `UInt` of `UInt64`, and `Byte` of `UInt8`, on every target. For width `w`, `Intw` has range `[-2^(w-1), 2^(w-1)-1]` and `UIntw` has range `[0, 2^w-1]`. Native pointer widths do not alter these aliases. `Char` is one Unicode scalar value (U+0000–U+10FFFF excluding surrogates); `Bool` has exactly `false` and `true`.

Integer overflow is never undefined behavior. Ordinary arithmetic is checked as specified below; wrapping, saturating, widening, and recoverable checked-result operations are separate explicit APIs.

Decimal arithmetic and decimal literal policy remain deferred.

### 6.1.1 Primitive operator typing and evaluation

Ordinary binary arithmetic requires operands of the same numeric type after literal inference; there are no implicit numeric promotions. Operators on already typed values never insert a conversion. Unary `+` preserves a numeric value; unary `-` is available for signed integers and floats, and is rejected for `UIntw` and `Nat`. Binary operand evaluation is left-to-right, exactly once, before the primitive operation. All operators below have an empty effect row; specified arithmetic defects follow §20 rather than producing an exception, `Result`, or `diverge`.

| Operands | Operators | Result and behavior |
|---|---|---|
| Same `Intw`/`UIntw` | `+`, `-`, `*` | Same type; compute the mathematical result and defect if outside its range |
| Same `Nat` | `+`, `*` | Exact arbitrary-precision `Nat` |
| Same `Nat` | `-` | Exact `Nat`, or defect for a negative result |
| Same integer type or `Nat` | `/`, `%` | Same type; quotient truncates toward zero, remainder satisfies `a = q*b + rem` and has the dividend's sign or is zero |
| Signed integer | unary `-` | Same type; defect when negating the minimum value |
| Same float type | `+`, `-`, `*`, `/`, unary `-` | Same type; §6.1.2 |
| Same numeric type | `==`, `!=`, `<`, `<=`, `>`, `>=` | `Bool`; mathematical integer order or §6.1.2 float comparisons |
| Same `Char`, `Text`, or `Bytes` | `==`, `!=`, `<`, `<=`, `>`, `>=` | `Bool`; scalar-value order for `Char`, lexicographic scalar sequence order for `Text`, unsigned byte sequence order for `Bytes` |
| Same `Bool` or `Unit` | `==`, `!=` | `Bool`; equality of Boolean values, and all `Unit` values equal |

Integer division or remainder by zero defects. Signed `MIN / -1` defects because the quotient is unrepresentable; `MIN % -1` yields zero without overflowing. For unsigned integers and `Nat`, division is floor division because operands are nonnegative. Float `%`, Boolean ordering, arithmetic on text, and operators on user nominal types are rejected; explicit functions/trait methods provide those operations. `!=` is the Boolean complement of `==`. Each comparison precedence level is non-associative; mixed levels follow §2.7, while repeated comparisons at the same level require explicit separate computations. Logical negation uses the predefined pure function `not(Bool) -> Bool`; `!` remains algebraic dispatch.

The nonnumeric forms in §2.7 retain their own contracts: calls/member access (§§4, 8, 10), access-prefixed methods (§14), turbofish (§2.4), `?` (§21.3), and optional access/coalescing (§21.6). `option ?? fallback` consumes one logical `Option` value, returns its owned `Some` payload or evaluates and returns `fallback` for `None`; ordinary `Dup` may preserve a bound source. Both alternatives obey the branch-join rules, and `fallback` must have the payload type. No fallback evaluation occurs for `Some`.

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

The compiler defines intrinsic constraints over non-type semantic categories when they expose an already-derived property rather than a user-defined protocol. In 0.0.2 this includes `NonAbandoning : EffectRow -> Constraint`, defined normatively in §17.3. It is not a trait and cannot be implemented by user code.

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
fn apply<A, B, !e>(f: fn(A) ->{e} B, value: A) ->{e} B;
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

Data-field projection `receiver.field` returns an ordinary value while preserving a bound receiver. It MUST require the selected field's type to satisfy `Dup`; the aggregate itself need not be `Dup`. Projection never moves a field out of a retained aggregate, creates a partially moved aggregate, or returns a reference/access-grant value. Field visibility and ordinary active-access checks still apply. Receiver-consuming method calls follow §10.4 instead.

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

The owned-pattern alternatives use §8.4. Reading a non-`Dup` field without taking ownership uses an explicit scoped projection API (§15).

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

For this finite fragment, an occurrence beneath any function type (including its result), raw pointer, aliasable mutable identity, associated projection, or constructor parameter with unknown storage behavior is not a finite strictly positive occurrence and is rejected. Recursive occurrences in GADT constraints or result indices are also rejected; the constructor's outer result must be the declared enum, while indices not mentioning the recursive group may vary as in §8.3. This is a conservative storage-based positivity rule, not a variance assumption inferred from a callable's effect row.

A nominal constructor's finite positive parameter profile is derived from its representation: a parameter qualifies only when every occurrence is in the storage positions above. Phantom parameters qualify but introduce no stored subvalue. For a GADT, a parameter profile is certified only when every constructor result uses the enum's indices uniformly as distinct corresponding parameter variables and constructor equalities have been propagated into payload types. If any constructor computes or refines those indices, no parameter positions are certified; the GADT may still be inductive through its direct recursive payloads. An index is not presumed phantom merely because it is absent under its source name from a payload. For mutually recursive declarations, begin with all candidate positions and repeatedly remove positions failing the rule until a fixed point; then check recursive group occurrences against the resulting profiles. Primitive identities and opaque runtime/foreign abstractions have compiler/audited profiles, defaulting to no certified storage positions. Unknown higher-kinded parameters have no such profile. The derived profile is canonical interface data when clients need it to check a recursive declaration; opacity does not permit clients to assume positivity.

Recursive transparent type aliases are rejected rather than introducing equi-recursive types. Nonrecursive nominal data may contain ordinary function values and mutable identities. Its existence does not make those values finite inductive subterms. A recursive group's runtime values consist of finitely many stored constructor nodes; safe construction cannot tie a cyclic stored-value knot. Foreign identities or mutable graphs may represent cycles through their own explicit abstractions, but traversing those identities does not use this inductive guarantee.

For example, `enum Chain<T> { End, Link(T, Chain<T>) }` is admitted. A recursive payload `fn(Bad) -> Int`, `fn() -> Bad`, `Ref<Bad,@r>`, or `F<Bad>` for an unconstrained constructor parameter is rejected. A visible finite nominal container may contain recursive children only in its certified storage positions.

## 9. Usage and intrinsic permissions

### 9.1 Fundamental predicates

Eldude recognizes two compiler-governed predicates:

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

Mutable-owner status is not a user-implementable trait and does not participate in trait resolution. It is an intrinsic semantic fact of designated nominal state abstractions and is exported in canonical interfaces when clients need to form root `mut` grants. `DynArray<T,@r>` is the canonical standard example. Scoped projection (§15) may derive a `mut T` grant to an arbitrary subvalue from an already active parent-owner grant; the derived grant retains the parent owner identity/projection path and does not require `T` itself to satisfy `MutableOwner`. The 0.0.2 core does not define a general user-extensible mechanism for minting new root mutable-owner identities; abstractions that require new identity mechanisms are built from existing state primitives or audited unsafe/runtime facilities until such a mechanism is independently justified.

Root-grant formation accounts for `state<@r>` under §14.3. The grant carries that accounted state authority through forwarding and projection; the target type of a projected grant need not name the parent region.

## 10. Traits

### 10.1 Coherent constrained polymorphism

Traits provide constrained polymorphism:

```eldude
trait Eq<T> {
    fn eq(left: T, right: T) -> Bool;
}
```

Resolution MUST follow the decidable rules of §§10.6–10.8 and MUST be independent of import order. Declarations outside that fragment are rejected even if a compiler could establish termination by another method. Runtime `diverge` never permits nonterminating static checking.

### 10.2 Implementation ownership

An implicit implementation MUST be declared in the module defining either:

- the trait; or
- the nominal head type.

This rule ensures a canonical implementation index compatible with direct-import separate compilation.

Overlapping implicit implementations are rejected using the head-only test of §10.6; prerequisites do not disambiguate overlapping heads.

Alternative behavior uses explicit wrappers or dictionary values.

### 10.3 Associated types and GATs

Associated types and generic associated types are supported subject to the equation-admissibility and normalization rules of §10.8. Each implementation supplies one equation for each associated declaration, including every GAT. A GAT equation binds the declaration's additional parameters without separately specializing them; specialization is determined solely by the enclosing implementation head.

```eldude
trait Collection<C> {
    type Item;
}
```

### 10.4 Method lookup

Inherent methods live in `impl Type { ... }`. Trait methods are selected from deterministic statically known candidate sets.

Method-call syntax selects the receiver mode before name/type resolution:

```eldude
value.method(args)          // self
view value.method(args)     // view self
mut value.method(args)      // mut self
```

None of these forms searches arbitrary free functions. Ambiguity after ordinary deterministic candidate selection is an error. The parser does not inspect the selected method declaration to decide which form was written.

### 10.5 Receiver modes

Methods declare the same receiver modes as ordinary parameters:

```eldude
self
view self
mut self
```

A call must use the corresponding syntactic form from §10.4. `view` and `mut` on method calls establish the same call-scoped grants as explicit ordinary arguments; dot syntax does not implicitly create a grant. Access-prefixed receivers are bindings rather than arbitrary computed expressions, matching the non-reified access model. A consuming `self` call is written without an access prefix.

No receiver mode creates a first-class reference.

### 10.6 Implicit implementation patterns and selection

An implementation head consists of the canonical trait identity, its arguments, and the implementing receiver type. The receiver is either a nominal application or a type parameter; the implementation-ownership rule of §10.2 still applies. Head patterns are finite, kind-correct first-order applicative terms: parameters, canonical nominal/primitive constructor identities, and their applications, including tuple and monomorphic function-type constructors. They exclude `forall`, associated projections, and type-level computation. Named higher-kinded parameters may occur in applications; matching never synthesizes a type lambda. Transparent aliases are expanded first and recursive alias expansion is rejected.

Region, effect-row, capture-row, and natural slots in a head or searched prerequisite contain only a parameter or a canonical constant of that category. Natural constants are literal indices. Closed rows are treated as canonical constants; matching does not split rows or solve arithmetic equations. Constructor parameters range over named constructors or other constructor parameters, not partially applied associated families or computed type functions. These restrictions concern implicit matching, not ordinary annotated signatures.

Head overlap is decided by renaming both heads' parameters apart and applying kind-correct first-order unification, with an occurs check, to their receiver and trait-argument terms. Two heads for the same trait overlap exactly when that unification succeeds. All visible headers in the canonical index are checked, independent of import order and of their prerequisites. Conflicting headers are rejected at the module boundary that first brings them together.

Selection uses one-way matching: only the implementation's parameters may be instantiated; the goal's abstract parameters and unresolved projections are rigid. Exact evidence in the local constraint environment is used first. Otherwise zero matching heads leaves an unsatisfied obligation, and one matching head is selected and its substituted prerequisites must all be discharged. Goals containing inference variables are postponed until ordinary inference fixes their relevant structure; they are never resolved by guessing an implementation. A remaining obligation must be supplied by a declared bound or is rejected at the checking boundary.

### 10.7 Decreasing implementation prerequisites

For a head or prerequisite, its argument terms include both the receiver and all trait arguments, excluding the trait name. Define `size` as the total number of nodes in their first-order applicative term trees: each parameter/constant and each application node counts once. Let `occurs(v, terms)` count occurrences of parameter `v` in those terms.

Every prerequisite generated by an implicit implementation, including intrinsic predicates and equalities, MUST be projection-free after alias expansion. Every user-trait prerequisite `P` of implicit implementation head `H` additionally MUST satisfy:

```text
size(P.arguments) < size(H.arguments)
for every parameter v: occurs(v, P.arguments) <= occurs(v, H.arguments)
P.arguments contain no associated projections or type-level computation
```

Aliases are expanded before these checks. Every parameter in a prerequisite must therefore occur in the head. Each prerequisite is checked independently; several smaller prerequisites are permitted. The same rule applies when the prerequisite names a different trait. This strict decrease is preserved by substitution of normalized terms, so mutually recursive trait declarations cannot create an infinite prerequisite chain.

Compiler-governed constraints such as `Dup`, `Discard`, and `NonAbandoning` use their intrinsic judgments, not user implementation search. They cannot introduce a dependency back into that search. Generic signatures may state explicit bounds involving projections; the prohibition above applies to prerequisites generated by implicit implementations. Trait-level bounds, where present, are expanded into each implementation's prerequisites before checking; recursive bound expansion is rejected.

For example, `Eq<List<T>>` requiring `Eq<T>`, or `Eq<Pair<A,B>>` requiring each component's `Eq`, decreases and is admitted. `Needs<List<T>>` requiring `Needs<List<List<T>>>`, and `A<T>` requiring `B<T>` on the same argument structure, are rejected. A prerequisite duplicating a parameter more often than the head is rejected even if its written size is smaller.

### 10.8 Associated equations and normalization

An associated projection is identified by its canonical trait/member, receiver, trait arguments, and any GAT arguments. Its equation's input terms are the enclosing implementation head's receiver and trait arguments followed by the GAT parameters. Associated-member names do not contribute to input size.

For every further associated projection `Q` in an equation's right-hand side, its input terms MUST be projection-free and satisfy both `size(Q.inputs) < size(equation.inputs)` and the parameter-occurrence condition of §10.7. Known acyclic aliases within the implementation are expanded before this check; recursive local associated aliases are rejected. Declared GAT-local bounds are expanded into each equation's obligations: all are projection-free after permitted alias expansion, and every user-trait obligation satisfies the same size/occurrence decrease against the equation's full input terms. The output may freely construct nominal types and repeat parameters outside further projection inputs. Changing the associated member or trait does not exempt a projection from decrease.

Thus the schematic equation `Flatten(List<T>) = List<Flatten(T)>` is admitted, while `Loop(T) = List<Loop(T)>` and `Loop(T) = Loop(List<T>)` are rejected. GAT arguments participate in the comparison, so shrinking a receiver while arbitrarily growing another argument does not establish decrease.

Normalization is deterministic: normalize projection inputs from left to right, select the unique equation by §10.6, substitute its inputs, and normalize the resulting type from left to right. Equation selection records the enclosing implementation's trait obligation and substituted prerequisites; all obligations must be discharged before the type is accepted. An equation is not permission to erase an unsatisfied bound. All implementation-generated prerequisites and GAT-local bounds are projection-free (§10.7), so equation reduction may generate trait obligations but recursive trait search cannot generate fresh projection computations.

A projection with an abstract receiver and no applicable equation remains an opaque, kinded term. Equality may use an explicit associated equality supplied by the local contract, or compare identical opaque terms; it MUST NOT infer a receiver or implementation by inverting an associated equation. Explicit equality substitutions require an occurs check and acyclic expansion, including occurrences beneath projections. No recursive equality expansion is permitted. A stuck projection is not itself an error, but a required equality not established by these rules is rejected.

This establishes finite normalization and prerequisite search for admitted declarations. Implementations may cache results or change evaluation scheduling while preserving these decisions. A compiler-specific depth/fuel limit is a resource limit, not an alternative language-admissibility rule.

## 11. Dynamic trait abstraction

### 11.1 `any Trait`

`any Trait` is an explicit runtime-dispatched package.

```eldude
any Parser<Token = Token>
```

Creating such a package is explicit; there is no universal implicit coercion.

### 11.2 Dynamic compatibility

Dynamic compatibility is a closed static judgment over the erased package interface. Write conceptually:

```text
StaticEnvironment ⊢ DynCompatible(any Trait<Args... associated bindings ...>)
```

The judgment is decided from the canonical interface of the trait plus the package's visible arguments/bindings. Imported implementation bodies are never consulted. Because 0.0.2 has no syntax for excluding individual trait methods from dynamic dispatch, every method of the trait must satisfy the method rule below; otherwise that `any Trait<...>` type is ill-formed.

For a candidate package interface `P = any Trait<...>`, each trait method `m` is dynamically compatible exactly when all of the following hold after substituting the trait arguments and package associated-type bindings supplied by `P`:

1. `m` has exactly one ordinary Eldude receiver: `self`, `view self`, or `mut self`.
2. `m` declares no method-local generic parameter of any Eldude generic category (`Type`, type constructor, `Region`, `EffectRow`, `CaptureRow`, or `NatIndex`). A higher-rank value type nested inside an otherwise closed parameter/result type is permitted; the prohibition is on generic parameters introduced by the dynamically dispatched method itself.
3. The distinguished concrete type variable `Self` occurs nowhere in the substituted callable contract except as the receiver. In particular, a parameter or result whose type is raw `Self` is not dynamically compatible.
4. No GAT projection occurs in the substituted callable contract.
5. Every ordinary associated-type projection used by a parameter, result, constraint, effect/capture relation, or other client-visible part of the callable contract is fixed by the package interface or canonically reduces to a package-visible type. No unresolved associated projection remains after substitution.
6. Every method-specific static constraint remaining after substitution is provable from the package interface alone. Dynamic invocation does not introduce an additional trait-search obligation whose truth depends on discovering the hidden concrete `Self`.
7. The method's parameter/result types, effect row, continuation-control envelope, and result-capture transformer are well formed using only package-visible static information, ordinary argument/capture variables, and the abstract capture/provenance summary of the receiver package. They MUST NOT refer to the hidden concrete nominal identity, representation, or a hidden `Self`-specific static fact.

These conditions define `DynCompatible`; there is no additional implementation-defined notion of “supported” or “representable”. A trait that fails them may still be used statically. Code needing runtime erasure must instead use a dyn-compatible trait, an explicit wrapper/dictionary, or nominal opacity.

Examples:

```eldude
trait Source {
    type Item;
    fn next(mut self) -> Option<Self::Item>;
}

// Potentially well formed when Item is fixed:
any Source<Item = Token>
```

The empty row of `next` permits in-place advancement through its supplied `mut self` grant and admits no additional effects (§14.3). A direct call forming a root grant to an erased mutable owner charges that owner's region state; dispatch through an existing projected grant preserves its supplied authority. Neither rule requires inspecting the hidden implementation body.

An implementation of this empty-row `Source::next` MUST be valid for every admissible supplied grant, including projection from a different owner/region. Advancement that requires an independent state identity's effect is incompatible with this method contract and MUST be rejected. For example, placing an erased owner tied to `@s` inside an array in `@r` does not let its implementation mutate independent `@s` state under an empty row using the projected `@r` authority. Supporting that behavior requires the state effect in the trait's public callable contract; retained package provenance does not substitute for it.

After substituting `Item = Token`, the method exposes no concrete `Self` outside the receiver. By contrast:

```eldude
trait CopyOut {
    fn copy(view self) -> Self;
}

trait GenericMap {
    type Item;
    fn map<U>(view self, f: fn(Self::Item) -> U) -> List<U>;
}
```

`any CopyOut` is ill-formed because `Self` remains in the result, and `any GenericMap` is ill-formed because `map` introduces the method-local type parameter `U`. A trait method that exposes a GAT projection is likewise statically callable but makes the trait ineligible for `any` in the 0.0.2 core.

A dynamically callable `mut self` method does not make every erased package a root mutable owner. Direct root `mut` access to the package is available only when packaging preserves compiler-recognized mutable-owner status/provenance; a package reached through an existing projected `mut` grant may use that derived grant normally.

### 11.3 Usage guarantees

A bare `any Trait` makes no `Dup` or `Discard` promise and is conservatively non-duplicable and non-discardable.

Stronger erased values state guarantees explicitly:

```eldude
any Source + Discard
any Source + Dup + Discard
```

Packaging checks the hidden concrete value against the advertised predicates.

A bare `any Trait` is an ownership-bearing erased package and may itself be a linear obligation. APIs intended for general heterogeneous storage or results that callers may abandon SHOULD request `+ Discard` explicitly. A public API returning a non-`Discard` erased package SHOULD expose an evident consuming or discharge operation; tooling SHOULD warn when an exported erased obligation appears to have no usable consumption path. This guidance is ergonomic and does not add another static permission predicate.

### 11.4 Erasure preserves obligations

Erasure hides the concrete nominal type and representation only.

It MUST preserve, in the static package contract:

- usage guarantees;
- capture/provenance obligations;
- region retention;
- required associated-type equalities;
- effects and result-capture relationships of dynamically callable methods;
- mutable-owner status/provenance when a dynamically callable `mut self` method requires it.

`any` cannot be used to hide a region escape, taskgroup provenance, or resource obligation.

# Part III — Function Values, Captures, and Call-Scoped Access

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
- a linear callable must be invoked exactly once, transferred to another owner, or consumed by an explicitly specified ownership-preserving structural-discharge protocol before the enclosing completed path ends. This last alternative is available only when the callable representation/interface or an audited intrinsic provides that operation (§56.2.1); ordinary function values have no generic environment-extraction or discard operation.

Eldude has no separate `Fn`, `FnMut`, `FnOnce`, `once fn`, or affine-function arrow.

### 12.4 Higher-order generic constraints

A higher-order implementation that may invoke a callback multiple times requires the callback environment to be duplicable. One that may skip and abandon the callback requires discardability; returning the callback obligation or structurally consuming it is a different ownership-preserving contract. For retained callbacks the complete lifecycle, including close/cancellation, determines this requirement (§56.2).

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
    f: fn(T) ->{e} Unit captures {..C},
) ->{e} Unit
where e: NonAbandoning,
      ..C: Dup + Discard;
```

`NonAbandoning` is the intrinsic effect-row constraint of §17.3. It does not constrain which ordinary effects may occur except through their already-declared continuation behavior.

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
    f: fn() ->{e} A captures {..C},
) -> fn() ->{e} A captures {..C};
```

### 13.4 Result-capture relationships

Callable-environment captures and result captures are distinct facts. Every function or method semantic contract therefore has a result-capture transformer `ResultCaptureTransformer` that maps tracked provenance of its argument values (including values targeted by `view`/`mut` arguments) and callable environment to the capture/provenance summary of the returned value. Conceptually:

```text
ResultCaptures = ResultCaptureTransformer(CallableCaptures, Argument1Captures, ..., ArgumentNCaptures)
```

`ResultCaptureTransformer` is part of the semantic callable contract even when ordinary source syntax does not display it. The compiler normally infers it from a body. A public or first-class callable whose result provenance affects client validity MUST carry a stable transformer in the canonical interface. This is what lets a separately compiled caller know, for example, that `fn(Ref<T,@r>) -> any Trait` returns an erased package retaining `@r`.

For an access-mode argument, its input capture summary describes the accessed value, not the grant or its authority. An ordinary value legally copied through a grant, such as a duplicable field (§8.1), retains its own provenance and may be returned subject to ordinary escape checks. The grant and its authority cannot escape. Thus returning an erased field that retains `@r` through `view holder` must preserve `@r` in the result contract even when the holder itself is non-`Dup`.

When no more precise relation is available for a bodyless declaration, the safe default is conservative: up to the provenance that the result type/package is capable of retaining, the result is assumed to retain the tracked captures of every argument value (using the accessed value for an access-mode argument) and of the callable environment. Statically capture-free result types remain capture-free. Foreign declarations and other trusted boundaries may state a more precise result-capture relation only as part of their audited semantic contract.

This relation reuses capture rows and provenance atoms; it is not a source lifetime language.

### 13.5 Retention horizons

Every lexical provenance atom has an internal validity horizon determined by lexical scope, even though no outlives syntax is exposed. A retaining owner may safely retain a provenance atom only while that atom remains valid.

Freely aliasable mutable storage requires a fixed horizon because existing aliases cannot have their static capture summaries retroactively changed. For `Ref<T,@r>`, construction and every payload-replacing write MUST therefore reject a value whose tracked region, taskgroup, lexical effect-instance, foreign, or runtime provenance can end before `@r`. Equivalently, every provenance retained by the payload must outlive or equal the cell's region horizon.

This rejects storing a task handle from an inner taskgroup or a value tied to an inner region in an outer `Ref`, while allowing an inner cell to retain values whose provenance is valid for longer than the cell. It is an internal scope-order check, not region subtyping or a user-visible lifetime relation.

### 13.6 Canonical interfaces

The compiler may infer local capture summaries and result-capture transformers. Public values/callables whose correctness depends on nonempty or polymorphic captures MUST expose stable capture relationships in the canonical interface.

The standard toolchain MUST also render every client-relevant result-capture transformer in a deterministic human-readable generated form. The generated notation is interface/diagnostic notation, not required author-written source syntax and not a lifetime language. A normalized relationship is rendered as an upper bound, conceptually:

```text
result-captures <= { captures(cell), captures(callback), ..C, @r }
```

where an entry `captures(x)` means the tracked capture/provenance summary of the named argument value or callable environment source; for a `view`/`mut` argument it denotes the accessed value, not the grant. `..C` is an existing capture-row parameter, a named provenance atom such as `@r` may appear directly, and the braces denote union. `{}` denotes a capture-free result. The rendered relationship MAY conservatively overapproximate the internally inferred `ResultCaptureTransformer`, but MUST NOT omit provenance that could change client validity. If the exact transformer cannot be expressed in this normalized algebra, the toolchain MUST render a safe conservative union rather than an opaque compiler variable.

### 13.7 Diagnostics

Illegal escape diagnostics SHOULD show a concrete retention path, for example:

```text
result -> closure -> parser -> Ref<State,@scratch> -> @scratch
```

rather than only an internal capture variable.

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

`mut` grants exclusive in-place access for one dynamic call. A root grant formed directly from an owned value requires the intrinsic mutable-owner judgment from §9.5; non-duplicability alone is not sufficient. A projected grant produced from an already active parent `mut` grant may target an arbitrary subvalue type and retains the parent owner identity/projection path.

The grant cannot be stored, returned, captured, or reified.

`mut` is not a general mechanism for aliased shared state. Shared mutable identity is represented by explicit types such as `Ref`.

`mut` carries call-scoped state authority as well as exclusive access. Its effect accounting is normative:

- Forming a root grant from an owned value satisfying `MutableOwner<T,@r>` MUST add `state<@r>` to the enclosing call expression's effects, regardless of the callee's written row. This is an upper bound even if the callee does not update the value or a conditional projection misses.
- A callee's `mut` parameter receives the caller-supplied grant and its authority. In-place updates to the granted storage, including updates through derived projections, require that authority but add no separate state entry to the callee's residual row. The parameter need not expose the parent region in its type or declare a region parameter for this purpose.
- Forwarding an active grant into another call, or deriving a projected grant, preserves its parent owner, region, projection path, and state authority. It does not form a new root grant or add a state effect solely for supplying that access. The original root charge remains in the enclosing computation.
- Supplied authority covers only the granted storage. Operations on independent mutable identities, including an aliasable `Ref` reached through the granted value, retain their ordinary effects even when those identities occupy the same region. Creating a new owned root grant also requires its own state accounting. Every effect explicitly admitted by an invoked callable's row MUST be propagated normally; `mut` never subtracts a declared state entry.

For example, projecting an element of `DynArray<DynArray<Int,@s>,@r>` preserves the outer grant's `@r` authority for the element slot. It does not confer authority over the inner array's independent `@s` identity. Mutating that identity retains `state<@s>` through the inner array API's ordinary effect contract; it cannot be classified as a row-free slot update merely because the inner owner was reached by projection.

Every callee body MUST be valid under any supplied grant admissible for its parameter modes/types, including a projection whose parent region differs from a region named by the target type. Knowing that the parameter type has `MutableOwner<T,@s>` status does not establish that the supplied grant is rooted at that independent owner or authorize its state outside the granted storage.

Thus `fn(mut T) ->{e} R` declares additional effects under its explicit access requirement. An empty row permits updates through the supplied grant; invocation on an owned root still admits `state<@r>`. This interpretation applies uniformly to ordinary parameters, callbacks, inherent methods, and statically or dynamically dispatched `mut self` methods. It is not a general state-effect handler or erasure rule: an accounted state entry is eliminated only by its non-escaping region boundary.

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
    f: fn(view T) ->{e} R captures {..C},
) ->{e} Option<R>
where ..C: Discard;
```

For a mutable owner:

```eldude
fn withMut<T, @r, R, !e, ..C>(
    mut values: DynArray<T, @r>,
    index: Int,
    f: fn(mut T) ->{e} R captures {..C},
) ->{state<@r>, e} Option<R>
where ..C: Discard;
```

The projected `view`/`mut` grant exists only during the callback invocation and cannot escape. A projected `mut T` grant carries the parent mutable owner's identity plus a non-overlapping projection path; it does not assert that `T` is independently a root mutable owner.

The callback receives the parent's state authority under §14.3, so updates through the projected grant need not add `state<@r>` to `e`. The explicitly declared `state<@r>` on `withMut` remains a conservative API effect even when its receiver is an existing grant. At a root call, union with the root-grant charge is idempotent. The same accounting applies to ownership-preserving and multi-element mutable projection forms.

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
    f: fn(view T) ->{e} R captures {..C},
) ->{e} Projection<
    R,
    fn(view T) ->{e} R captures {..C}
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
    f: fn(view T, view T) ->{e} R captures {..C},
) ->{e} Option<R>
where ..C: Discard;

enum ProjectionError {
    Bounds,
    AliasedIndices,
}

fn withMut2Distinct<T, @r, R, !e, ..C>(
    mut values: DynArray<T, @r>,
    left: Int,
    right: Int,
    f: fn(mut T, mut T) ->{e} R captures {..C},
) ->{state<@r>, e} Result<ProjectionError, R>
where ..C: Discard;
```

The mutable form invokes the callback only after proving both indices are valid and denote non-overlapping projections; equal/conflicting indices produce the ordinary failure result. Ownership-preserving variants may return the callback on failure as in §15.4. These APIs reduce callback nesting without creating reference values or a general borrow language.

### 15.6 No general first-class non-owning slice

Eldude does not currently define a general `Slice<T,@r>` or equivalent first-class view into a mutable owner's interior. Such a type would require invalidation rules equivalent to a long-lived borrow discipline.

Owning immutable subviews may be provided by library types when their ownership and usage semantics are explicit. Mutable-owner interior access uses scoped projection.

# Part IV — Effects, Non-divergence, Failure, and Handlers

## 16. Effect rows

### 16.1 Function effect syntax

Function arrows may carry effect rows:

```eldude
fn(A) -> B
fn(A) ->{fs} B
fn(A) ->{fs, diverge} B
fn(A) ->{e} B
fn(A) ->{fs, e} B
```

The empty row is omitted.

Rows are canonical unordered upper bounds. A computation with a smaller row may be used where a larger admitted row is expected, subject to normal variance and constraint rules.

For a callable with `mut` parameters or receiver, the written row is interpreted under the supplied access authority (§14.3). The complete effects of a call also include state charges for root grants formed at that call (§59.3); an empty written row alone does not make such a root invocation pure.

### 16.2 Effect-row polymorphism

An effect-row parameter is declared with `!`:

```eldude
fn apply<A, B, !e>(
    f: fn(A) ->{e} B,
    value: A,
) ->{e} B;
```

Inside an effect-row context, the variable is written `e`, not `!e`.

### 16.3 Effect categories

Eldude distinguishes three semantic categories of row entry.

**Algebraic effect families** are declared with `effect` and may be interpreted by handlers.

**Intrinsic semantic effects** are compiler/runtime effects that are not user-handleable algebraic families. The current design includes at least:

```text
diverge
suspend
```

**Region state effects** have the form:

```text
state<@r>
```

They track mutable identity in a region and are eliminated only by the corresponding region boundary when non-escape is proved.

For updates through call-scoped `mut` access, the root invocation accounts for region state and the supplied grant carries that authority into callees (§14.3). Forwarding or projection does not erase the original charge, and independent state operations retain ordinary row accounting.

### 16.4 Direct operations versus ordinary calls

A direct algebraic operation uses `!`:

```eldude
!Console::print("hello");
```

An ordinary effectful call does not:

```eldude
readFile(path)
```

The leading `!` identifies algebraic operation dispatch, not general effectfulness.

## 17. User-defined algebraic effects

### 17.1 Effect declarations

Every operation declares exactly one resumption mode:

```eldude
effect Console {
    tail print(text: Text) -> Unit;
    once readLine() -> Text;
}
```

An operation whose semantics are abortive is written as an `affine` operation returning `Never`:

```eldude
effect Raise<E> {
    affine raise(error: E) -> Never;
}
```

There is no separate `abort` mode. Because safe Eldude cannot construct a `Never` value, a handler for `raise` cannot take the resuming path; every terminating handler path chooses zero resumptions. The ordinary affine abandonment rule therefore supplies the complete control semantics.

### 17.2 Resumption modes

The core modes are normative:

```text
tail
    exactly one resume, as the final semantic action of the clause

once
    exactly one resume; the clause may regain control afterward

affine
    zero or one resume
```

The declaration describes control behavior independently of the handler implementation. Many-shot resumption is not part of the 0.0.2 core and is listed as deferred in Appendix A.

### 17.3 Derived continuation-control envelope

Effect rows determine a compiler-derived continuation-control envelope used at opaque calls and other composition boundaries. In the 0.0.2 core, the envelope records whether evaluation may abandon the surrounding continuation. The envelope is evaluated relative to the current structural-control context `Control`, including whether cooperative cancellation is masked at the evaluation point.

For a closed effect row `Effects`, define `mayAbandon(Control, Effects)` as follows:

- `suspend` contributes an abandonment path exactly when cooperative cancellation is **not** masked by `Control`, because an actual unmasked suspension point may deliver cancellation;
- an algebraic effect family contributes an abandonment path when it declares at least one `affine` operation that can escape the relevant boundary; structural cancellation masking does not neutralize algebraic abandonment;
- `tail`, `once`, `diverge`, and `state<@r>` do not by themselves contribute an abandonment path.

In the ordinary unmasked structural control context `UnmaskedControl`, write `mayAbandon(Effects)` as shorthand for `mayAbandon(UnmaskedControl, Effects)`. An unconstrained open effect-row variable is conservatively treated as potentially abandoning in any context where its unknown families could contain `affine`; masking may remove only the known cancellation edge contributed by `suspend`.

Eldude 0.0.2 exposes exactly one source constraint on the **ordinary unmasked** derived property:

```eldude
where e: NonAbandoning
```

`NonAbandoning` is an intrinsic compiler-governed predicate over effect rows, not a trait, effect family, capability, or user-implementable protocol. A closed row satisfies it exactly when `mayAbandon(UnmaskedControl, Effects)` is false. An open row variable satisfies it when its generic constraint environment contains `e: NonAbandoning`; every substitution for that variable MUST itself satisfy the predicate. For a compound row such as `{state<@r>, e}`, the whole row is checked compositionally.

Thus generic code may quantify over unknown ordinary effects while ruling out continuation abandonment. A structural mask can make a particular execution context less abandoning than the row's unmasked contract without changing whether the row itself satisfies `NonAbandoning`.

At an ordinary call `f(...)` with admitted row `Effects`, the checker evaluates `mayAbandon(Control, Effects)` in the current structural context. If it holds, every continuation segment that may be abandoned must be a legal structural exit under §62.2. Handling an algebraic family locally removes the intercepted family from the residual row and therefore from the downstream envelope. The envelope is derived from effect declarations and existing structural masks already represented in `Control`; it is not another user-defined capability or effect axis.

Canonical cleanup and taskgroup-shutdown execution establish cancellation masks in `Control`. The same envelope rule therefore explains why `suspend` is non-abandoning *in those masked contexts* while residual `affine` control remains abandoning. No cleanup-specific or shutdown-specific effect classification exists.

### 17.4 Effect instances

At elaborated-core level, an algebraic operation belongs to an effect family plus an instance identity.

A `handle` expression creates a fresh instance for its inline lexical handler. Source code may name it when necessary:

```eldude
handle {
    !console::print("hello");
} with console = handler Console {
    print(text) => {
        terminalWrite(text);
        resume(());
    }

    readLine() => {
        resume(terminalRead());
    }
}
```

An unqualified operation such as:

```eldude
!Console::print(...)
```

selects the nearest unambiguous ambient instance of that family. Ambiguity is an error.

Named effect instances are lexical identities, not ordinary first-class values. If a closure retains one through lexical reference, that retention is tracked in its capture summary.

## 18. Intrinsic semantic effects

### 18.1 `diverge`

`diverge` means that evaluation may fail to return in finitely many abstract-machine steps under its declared contracts.

It includes at least:

- infinite computation;
- deadlock;
- indefinite blocking;
- unbounded retry;
- waiting on a dependency whose completion is not proved;
- foreign or host operations without a finite-return contract.

`diverge` cannot be handled by an algebraic handler.

### 18.2 `suspend`

`suspend` means that evaluation may reach an actual suspension point at which the current Eldude execution domain may schedule another strand.

Typical sources include:

```text
await
explicit task yield
suspending host wait
library/runtime operations documented to suspend
```

Every actual ordinary suspension point is a potential cooperative cancellation-delivery point unless the current structural context `Control` masks cooperative cancellation, as during canonical `Cleanup` execution or taskgroup shutdown. Eldude has no second `cancellable` versus `noncancellable` suspension property.

`suspend` cannot be removed by an algebraic handler merely by intercepting another effect family. A handler that implements an operation using a suspending computation contributes `suspend` to its residual row.

### 18.3 Upper-bound interpretation

An effect row states what may occur, not that every listed effect occurs on every execution.

A function typed with `{suspend}` does not cause cancellation merely by being called. Cancellation can be delivered only when execution actually reaches an ordinary suspension point, and only when cancellation is not structurally masked. Static checking must establish that cancellation at each such reachable point is a legal non-local exit under the ordinary obligation-discharge judgment.

## 19. Non-divergence

### 19.1 Default contract

Absence of `diverge` is a non-divergence guarantee under the declared contracts of primitives, handlers, the host, and foreign functions. It rules out admitted infinite computation, deadlock, indefinite blocking, unbounded retry, and equivalent nontermination; it does not promise normal return in the presence of explicit defects or externally delivered structural cancellation.

A function:

```eldude
fn(A) -> B
```

is pure and non-diverging in this semantic sense. Absence of `diverge` does not promise defect-freedom: evaluation may still terminate at an explicit nonrecoverable defect boundary rather than produce `B`, as described below.

### 19.2 Structural recursion

The compiler MUST accept recursion satisfying the following structural rule over finite inductive declarations of §8.5. In each mutually recursive function group, choose a common ordered vector of designated inductive parameter positions (one position is sufficient for ordinary list/tree recursion). At every call edge within the group, the argument vector must be lexicographically smaller: preceding components preserve the incoming component, one component is a proper stored subterm of its corresponding incoming component, and later components are unrestricted. The compiler checks the finite set of possible position vectors; an annotated `decreases` contract may instead supply the explicit measure of §19.3.

The structural-subterm relation is generated only by constructor decomposition of a known inductive value, including visible data-field reads of those same stored components (§8.1): each actually stored field/payload reached through finite positive storage positions is a direct subterm, and paths with at least one such decomposition are proper subterms. Pattern-derived equalities and non-consuming copies preserve the same relation; simple name aliases preserve it as well. Nested patterns compose paths. Matching a GADT may change indices without changing this stored-subterm fact.

Reconstruction, arbitrary function results, associated-type equalities alone, calls through stored functions, reads from mutable/foreign identities, and unspecified container accessors establish no structural-subterm relation. A new value equal by `Eq` to a child is not thereby a tracked child. Pattern inspection observes the same runtime constructor but still obeys the ownership rules of §8.4; termination evidence never grants duplication, discard, or access permissions. Imported bodies are not inspected to discover subterm relationships.

```eldude
fn length<T>(xs: LinkedList<T>) -> Nat
where T: Discard
{
    match xs {
        case LinkedList::Nil => 0;
        case LinkedList::Cons { head: _, tail } => 1 + length(tail);
    }
}
```

### 19.3 Explicit measures

Well-founded measures may be supplied:

```eldude
fn gcd(a: Nat, b: Nat) -> Nat
    decreases b
{
    if b == 0 {
        a
    } else {
        gcd(b, a % b)
    }
}
```

Loops may similarly state a decreasing measure.

### 19.4 `while`

A `while` loop is total only when the checker proves well-founded progress. Otherwise the enclosing computation admits `diverge`.

### 19.5 `for`

A `for` loop is total only when the iteration contract establishes a finite number of steps and the loop body is total.

Iteration over a potentially unbounded source admits `diverge` unless a finite bound is proved.

### 19.6 Elaborated control-dependency graph

Termination checking is not limited to syntactic recursion.

The compiler constructs or approximates an elaborated control-dependency graph containing relevant edges from:

- direct function calls;
- higher-order callable invocation;
- callable loads/stores through mutable state;
- algebraic operations and handler clauses;
- `resume`;
- explicit `!self` control cycles;
- forwarded effect paths;
- task-completion dependencies introduced by `await` or taskgroup drain;
- other control transfers capable of forming a semantic cycle.

Any strongly connected dependency whose well-founded termination cannot be proved contributes `diverge`.

When exact proof is unavailable, Eldude prefers conservative `diverge` over an unsound non-divergence guarantee.

### 19.7 Opaque indirect control dependencies

Any indirect control dependency whose producer provenance or well-founded termination cannot be established from the current semantic contract contributes `diverge`. This rule applies uniformly to at least:

- awaiting an opaque task;
- invoking a callable loaded from externally supplied mutable state;
- invoking a retained callback hidden inside an opaque value;
- following an opaque handler/control dependency whose cycle-freedom is not established.

For example:

```eldude
fn wait<T>(task: Task<T>) ->{suspend, diverge} T {
    await task
}
```

A direct local await of a known-total child may require only `suspend`. A private implementation may prove a more precise local dependency, but separate clients do not inspect that body. The initial architecture prefers conservative `diverge` rather than requiring canonical termination-dependency summaries; such summaries may be added later only if concrete programs justify the extra interface machinery.

### 19.8 External operations

Potentially blocking I/O, foreign calls, waiting on external peers, and equivalent operations admit `diverge` unless their contract proves finite return.

A timeout does not establish finite return if cancellation, shutdown, or cleanup may itself block indefinitely.

## 20. Defects and assertions

### 20.1 Assertions

Eldude provides one assertion form:

```eldude
assert condition;
```

The condition must have type `Bool`. Eldude has no build-erasable debug assertion construct.

### 20.2 Defect semantics

A failed assertion is a nonrecoverable defect termination.

A defect is:

- not `Result::Err`;
- not an algebraic effect;
- not a `panic` effect;
- not catchable by Eldude effect handlers.

A defect is catastrophic termination of the current Eldude execution path, not a recoverable non-local exit. Static usage checking therefore does not require arbitrary naked linear obligations to be consumed or transferred on a defect path: no Eldude continuation may recover those obligations after the defect. Deterministic discharge across defects is obtained by placing resources under explicit structural owners such as `using`.

The runtime nevertheless initiates best-effort structural unwinding: active `using` scopes perform required cleanup, active taskgroups shut down owned children, and region/runtime storage is released according to its structural rules. This structural unwinding does not retroactively make every naked linear value cleanup-owned.

Defect precedence is uniform across all structural discharge, not cleanup-specific:

- if the first defect is encountered while normal completion or a non-defect structural outcome (`return`, `?`, loop exit, affine zero-resumption, or cancellation) is pending, that defect becomes the primary outcome and the prior outcome becomes suppressed diagnostic context;
- once a defect is already primary, later defects encountered during cleanup, taskgroup drain, child cleanup, or equivalent structural discharge are recorded as secondary diagnostics;
- reachable outer structural discharge continues while possible.

If structural discharge diverges, no guarantee is made that later cleanup or the host defect boundary can be reached.

### 20.3 Proof status

Assertions are runtime defect checks, not theorem assumptions for the static semantics.

`assert` may not be required to justify:

- type safety;
- bounds safety;
- region or access safety;
- `Dup`/`Discard`/linearity or any ownership discharge;
- capture/provenance safety;
- non-divergence;
- optimization correctness.

Assertions are not build-erasable. Their evaluation follows the ordinary typing, effect, usage, and control rules, so build configuration cannot change ownership/effect behavior by removing an assertion.

### 20.4 No general-purpose panic

Eldude has no general-purpose recoverable or effect-typed `panic` mechanism.

Routine invalid input uses typed results, options, stronger input types, or explicit defects only when violation denotes an implementation/programming defect rather than expected failure.

## 21. Expected failure and nominal error composition

### 21.1 `Result`

Recoverable expected failure uses:

```eldude
Result<E, T>
```

`Result` is the standard representation for routine expected failure. Zero-resumption affine algebraic effects remain available for abstractions whose semantics specifically require dynamically scoped control; they are not a second standard exception convention.

`Err` is data.

### 21.2 Nominal error composition

Composable errors use ordinary nominal algebraic data. For example:

```eldude
enum LoadError {
    IO(IOError),
    Parse(ParseError),
}
```

Eldude 0.0.2 has no structural `error { ... }` type and no implicit nominal-error subtyping/widening. When a computation with error type `E1` must participate in an API using error type `E2`, the program performs an explicit mapping or constructs the chosen nominal variant.

This keeps expected failure within the ordinary nominal data model rather than introducing a specialized structural sum mechanism.

### 21.3 Postfix `?`

For:

```eldude
expr?
```

`expr` is evaluated exactly once and must produce `Result<E,T>` compatible with the nearest lexical propagation target.

On `Ok(value)`, the expression yields `value`.

On `Err(error)`, control transfers to the nearest lexical `try` boundary using the **same nominal error type `E`**; if none exists, the current function returns `Err(error)` and its declared result must use that same `E`.

### 21.4 No implicit semantic conversion

`?` performs only identity propagation of the current nominal error type.

Programmer-defined conversion code is never run implicitly by `?`. Nominally different errors require explicit mapping before propagation.

### 21.5 `try`

A lexical `try` creates a local `Result` propagation boundary:

```eldude
let result: Result<LoadError, Config> = try {
    let bytes =
        readFile(path).mapError(LoadError::IO)?;
    parse(bytes).mapError(LoadError::Parse)?
};
```

All `?` edges targeting one `try` boundary must carry the same nominal error type after any explicit mappings. Normal block completion becomes `Ok`. A propagated error becomes `Err` at that boundary.

`return` inside a `try` still returns from the enclosing function.

### 21.6 Optional access and coalescing

For `Option<T>`, optional member access uses `.?`:

```eldude
user.?address.?city
```

It does not implicitly flatten nested `Option` values.

For data fields, if `option: Option<T>` and visible field `field: F` belongs to `T`, `option.?field` has type `Option<F>` and MUST require `F: Dup`. It preserves a bound `option` and its payload: `None` yields `None`, and `Some(value)` yields `Some` of a copy of the field. If `F` is itself an `Option<U>`, the result is `Option<Option<U>>`. The receiver is evaluated once; a computed owned temporary additionally requires `Option<T>: Discard`, exactly as for ordinary field projection (§8.1). No field or payload ownership is extracted by this syntax.

Coalescing:

```eldude
option ?? fallback
```

evaluates `fallback` only for `None`.

## 22. Diagnostics and logging

### 22.1 `Diagnostic`

The standard library may define a pure trait conceptually equivalent to:

```eldude
trait Diagnostic {
    fn diagnostic(view self) -> DiagnosticRecord;
}
```

`DiagnosticRecord` is structured diagnostic data. Its exact standard-library field schema is not a core-language semantic requirement.

`Result<E,T>` accepts any `E`; `Diagnostic` is optional.

### 22.2 Logging

Logging is an ordinary standard-library algebraic effect, conceptually:

```eldude
effect Log {
    tail emit(record: LogRecord) -> Unit;
}
```

Convenience functions such as `log::info` or `log::error` are library APIs.

Assertions do not acquire a `Log` effect. A host may route defect diagnostics and log records to the same backend, but they remain distinct semantics.

`?` never logs automatically.

## 23. Lexical handler frames

### 23.1 Handlers are not first-class values

Eldude 0.0.2 has no public `Handler<...>` value type. A handler is a lexical interpreter block written only as part of a `handle` application:

```eldude
handle {
    greet()
} with handler Console {
    print(text) => {
        terminalWrite(text);
        resume(());
    }

    readLine() => {
        resume(terminalRead());
    }
}
```

The compiler infers the handled family, output type, residual effect row, retained captures/provenance, and result-capture relationship of the whole `handle` expression.

Reusable interpretation is expressed by an ordinary wrapper function that installs the lexical handler around a supplied computation. This reuses ordinary function types, captures, effects, and separate-compilation contracts instead of introducing a second first-class callable package.

Conceptually:

```eldude
fn withTerminal<A, !e, ..C>(
    body: fn() ->{Console, e} A captures {..C},
) ->{io, e} A
{
    handle {
        body()
    } with handler Console {
        print(text) => {
            terminalWrite(text);
            resume(());
        }

        readLine() => {
            resume(terminalRead());
        }
    }
}
```

The exact constraints required by a wrapper follow from the body, handler clauses, and ordinary continuation-control rules; the example is illustrative rather than a universal wrapper signature.

### 23.2 No hidden handler state

A lexical handler frame has no privileged hidden mutable fields.

Persistent state used by handler clauses must use ordinary Eldude state/resource abstractions and therefore participates in effects, captures, regions, and usage checking.

### 23.3 Active handler-frame obligations

Installing a lexical handler creates one active handler frame that owns every nontrivial value/provenance retained by its clauses for the duration of the `handle` evaluation. The frame has one ordinary usage state; deep re-entry does not create another logical owner of that state.

At a `resume` boundary, handler-frame ownership is threaded as follows:

- every non-`Dup` frame capture is **moved into the resumed computation**;
- those moved captures are unavailable to code in the resuming clause after `resume(...)` returns;
- a `Dup` frame capture may be semantically duplicated, allowing one copy to remain available to the clause while one is available to the resumed computation;
- the resumed computation, including re-entered clauses and any `return` clause reached while it runs, owns the moved frame state and must obey ordinary usage rules for it.

Therefore a `tail` resume naturally transfers all non-`Dup` frame captures because no code follows it. A `once` clause, or the resuming path of an `affine` clause, may continue after `resume`, but that post-resume continuation is checked with the moved non-`Dup` captures absent from its usage environment. It may continue using only captures that remained legally available (for example `Dup` captures) plus values produced independently by the resumed computation.

A terminal handler path discharges exactly the frame obligations that it currently owns. Normal return reached inside a resumed computation may therefore discharge the frame state moved into that resumption; when control subsequently returns to an outer `once`/`affine` clause, that outer clause does not reacquire those moved obligations. A zero-resumption `affine` path does not perform such a transfer and must discharge its locally owned non-`Discard` frame obligations itself.

This ownership-threading rule prevents deep re-entry and returning resumptions from duplicating or double-consuming linear/affine handler captures. For example, if a `once` clause calls `resume(())` and a re-entered `return` clause consumes a linear frame capture, code after that `resume` cannot consume or otherwise access the same capture; it was moved into the resumed computation.

## 24. Handler application and instances

### 24.1 Anonymous fresh application

```eldude
handle {
    greet()
} with handler Console {
    ...
}
```

creates a fresh anonymous instance of `Console`.

### 24.2 Named application

When the instance must be referenced explicitly:

```eldude
handle {
    computation()
} with console = handler Console {
    ...
}
```

`console` is the fresh lexical instance identity inside the handled body.

The source states the family once in the inline handler block.

### 24.3 Instance scope

The named instance is in scope in the handled body and its lexical descendants.

It is not in scope while constructing the handler clauses themselves. Inside handler clauses, the current instance is referred to as `self`.

An instance identifier cannot be returned or stored as an ordinary value. A closure that lexically references one retains that identity in its capture set and therefore cannot outlive the handler scope.

### 24.4 Deep handling

Handlers are deep. `resume(value)` reinstalls the same handler around the resumed computation, using the handler-frame usage state transferred by §23.3. Re-entry therefore shares the same logical frame ownership state rather than manufacturing a fresh copy of retained obligations.

Shallow handlers are not part of the current design.

## 25. Handler clauses and resumption

### 25.1 Lexical resumption

Each resumable clause has exactly one implicit lexical resumption capability. It has no user-denotable variable.

```eldude
print(text) => {
    write(text);
    resume(());
}
```

`resume(value)` is the only source syntax for resuming.

The resumption cannot be stored, returned, passed, captured by a nested closure, or otherwise escape the clause.

### 25.2 `tail`

A `tail` clause MUST resume exactly once and that resume MUST be its final semantic action.

Implementations SHOULD lower eligible tail operations without allocating a general continuation.

### 25.3 `once`

A `once` clause MUST resume exactly once. The clause may continue after the resumed computation returns, but its post-resume usage environment does not contain any non-`Dup` handler-frame captures moved into the resumption under §23.3.

### 25.4 `affine`

An `affine` clause may resume zero or one time.

If it does not resume, abandoning the captured continuation segment must be a legal non-local control exit under ordinary usage, cleanup, region, taskgroup, and capture rules.

### 25.5 Abortive affine operations

Eldude has no separate abort resumption mode. An `affine` operation returning `Never` is semantically abortive in safe code because no `Never` value can be supplied to `resume`.

Such an operation still uses the ordinary affine operation-site and zero-resumption abandonment rules; no additional continuation mode is introduced.

## 26. Handler completion, forwarding, and residual rows

### 26.1 Normal completion

A lexical handler may define:

```eldude
return value => expression;
```

If omitted, the compiler inserts identity and therefore requires the handled computation's normal result type and the `handle` expression's result type to unify.

### 26.2 Completeness

Handlers are complete by default. Every operation is either handled or explicitly forwarded.

```eldude
handle {
    computation()
} with handler Console {
    print(text) => {
        ...
        resume(());
    }

    forward readLine;
}
```

`forward ..;` forwards every otherwise omitted operation.

### 26.3 Forwarding

Forwarded operations target the next outer instance of the same family. If no outer instance exists, the family remains in the resulting effect row.

### 26.4 Same-family operations inside clauses

Inside a clause, an unqualified operation of the handled family is an error.

Explicit recursion to the current instance uses:

```eldude
!self::op(...)
```

Explicit outer-instance dispatch uses the named outer instance.

This prevents accidental self-recursion or forwarding.

### 26.5 Residual row

Every `handle` expression has a complete residual effect row, including:

- effects introduced by operation clauses;
- effects introduced by the return clause;
- intrinsic semantic effects introduced by handler implementation;
- the handled family itself if forwarding may leave it unhandled.

The residual row is part of the surrounding expression/function contract. There is no standalone handler-value type or hidden forwarding metadata required by downstream type checking.

### 26.6 Composition

Handlers compose by ordinary lexical nesting:

```eldude
handle {
    handle {
        computation()
    } with handler Database {
        ...
    }
} with handler Console {
    ...
}
```

There is no separate handler-list syntax.

### 26.7 No handler-specific cleanup

Handlers have no `finally` construct. Resource lifetime uses `using`, regions, and taskgroups.

# Part V — Regions, Mutable Identity, and Cleanup

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
fn size<@r>(view buffer: DynArray<Byte, @r>) -> Nat;
```

There is no region subtyping or source-level outlives relation.

### 27.3 Region state effect

Operations observing or mutating region identity use:

```text
state<@r>
```

`state<@r>` is an intrinsic unhandleable effect. It cannot be intercepted by `handler`.

A region boundary eliminates its own `state<@r>` effect when escape conditions are satisfied.

Updates through `mut` use the root-grant accounting of §14.3: the root call admits `state<@r>`, and callees operate under the supplied grant's authority. The region entry remains in the enclosing computation until region elimination. Aliasable-state operations such as `Ref` operations declare their state effects in the ordinary way; `mut` authority does not discharge those effects.

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
T ! {state<@r>, e}
```

and `@r` does not escape through `T`, captures, or obligations, the enclosing region expression has external effects `e`.

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

At an owned-root call, grant formation charges that state effect (§14.3). An API's explicit state row, as below, is also propagated on calls using a supplied grant.

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
T: Discard
```

This restriction ensures that region destruction and cell replacement cannot strand an undiscardable payload merely because multiple aliases exist.

Because aliases may already exist when a payload is changed, `Ref<T,@r>` also has the fixed retention-horizon rule from §13.5: every tracked provenance captured by an installed payload must remain valid for at least the lifetime of `@r`. This condition is checked at construction and on every payload-replacing operation.

A `Ref<T,@r>` handle is `Dup + Discard` and may therefore be freely aliased within the region's lifetime.

### 28.4 `Ref` operations

Representative operations are:

```eldude
fn new<T, @r>(value: T) ->{state<@r>} Ref<T, @r>
where T: Discard;

fn get<T, @r>(cell: Ref<T, @r>) ->{state<@r>} T
where T: Dup;

fn replace<T, @r>(
    cell: Ref<T, @r>,
    value: T,
) ->{state<@r>} T
where T: Discard;
```

`new` creates aliasable mutable identity in `@r` and therefore necessarily carries `state<@r>`; this also prevents local polymorphic generalization from manufacturing a polymorphic mutable cell. `replace` transfers ownership of the previous payload to the caller and installs the new value. The new value must satisfy the fixed retention-horizon check for `@r`; a shorter-lived taskgroup, region, effect-instance, or foreign/runtime provenance cannot be hidden in an outer cell.

An API that discards the previous payload may rely on the `Ref` construction requirement `T: Discard`.

There is no safe `Ref<File,@r>` when `File` is linear/non-discardable.

### 28.5 `view` and aliasable state

A `view` grant to an object containing or exposing a `Ref` does not freeze the referenced cell. Mutation through the explicit aliasable-state API remains possible and is visible through `state<@r>`.

`view` protects ownership/consumption, not observational constness of independent mutable identities.

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
    fn cleanup(self) ->{e} Unit;
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

Cleanup is discharge-only structural control. Entering canonical cleanup establishes the cleanup cancellation mask in the ordinary structural context `Control`, and the cleanup body is checked by the same context-relative continuation-control envelope of §17.3 as any other computation.

Under that mask, `suspend` contributes no cancellation-abandonment edge because pending cooperative cancellation is not delivered into the cleanup action. The mask does **not** neutralize algebraic abandonment: an escaping family containing `affine` remains abandoning and MUST be handled before leaving the cleanup invocation. `tail` and `once` operations obey their ordinary resumption and handler-frame rules.

A cleanup defect follows the general structural-discharge precedence rules in §20.2. Cleanup divergence may prevent the prior structural outcome and later cleanup from being reached.

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

For each still-live cleanup-owned binding, cleanup is initiated on every control exit crossing the scope, including:

- normal completion;
- `return`;
- `?` propagation;
- `break` or `continue` crossing the scope;
- affine zero-resumption algebraic control;
- cooperative cancellation;
- assertion-defect unwinding;
- abandonment of an affine continuation when the control-exit judgment permits it.

### 31.5 Cancellation protection

Once cleanup for a structural exit begins, cooperative cancellation is masked until the cleanup action returns or diverges.

If cleanup suspends, sibling strands may run, but pending cancellation is not delivered into that cleanup action.

After cleanup completes, pending cancellation continues outward.

### 31.6 Cleanup effects

Cleanup effects are ordinary effects at the lexical point of cleanup execution, subject to the discharge-only restriction in §30.5. An enclosing handler may interpret resumable cleanup effects; affine zero-resumption control may not escape the cleanup invocation even when an outer handler for that family exists.

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

# Part VI — Standard Library Collections and Iteration Profile

This part specifies the bundled standard-library collection profile and the language/library contracts used by `for` and scoped projection. The semantic core requires usage-preserving ownership behavior; the exact collection families, representations, and cost guarantees below are standard-library commitments rather than independent language mechanisms.

## 32. Standard sequence abstractions

### 32.1 `List<T>` (standard library)

`List<T>` is the default immutable finite dynamic-length sequence.

Its required semantic/cost contract is:

- contiguous logical element storage;
- value semantics;
- copy-on-write or equivalent retained sharing when usage permits;
- O(1) length;
- O(1) indexed element location;
- amortized O(1) append when representation can be reused;
- O(n) worst-case copy when retained sharing or growth requires it.

Under the bundled standard-library profile, list literals construct `List<T>`:

```eldude
[1, 2, 3]
```

### 32.2 `TreeList<T>` (standard library)

`TreeList<T>` is an immutable persistent tree-backed sequence intended for workloads retaining branching historical versions.

It provides structural sharing and logarithmic indexed update/access under a fixed branching-factor implementation contract.

### 32.3 `LinkedList<T>` (standard library)

`LinkedList<T>` is the canonical immutable cons structure, conceptually:

```eldude
enum LinkedList<T> {
    Nil,
    Cons { head: T, tail: LinkedList<T> },
}
```

Prepend/head/tail are O(1); length and indexed access are O(n).

### 32.4 `Array<T,N>` (standard library)

`Array<T,N>` is immutable statically sized contiguous storage. `N` is a `NatIndex`.

```eldude
Array<Byte, 32>
```

Under the bundled profile, list literals do not contextually become arrays.

Fixed shape is the point of the abstraction. Shape-changing insertion/removal is not part of the initial core `Array` API; code needing routine dynamic insertion/removal uses `List` or `DynArray`.

### 32.5 `DynArray<T,@r>` (standard library mutable-owner example)

`DynArray<T,@r>` is mutable growable contiguous storage owned in region `@r`.

It is never `Dup`. Direct mutation requires `mut` plus the region-state accounting specified in §14.3; its API's explicitly declared state effects remain admitted on forwarded calls.

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

`for` is total only when the source's iteration contract establishes finite completion and the body is total. Potentially unbounded iteration contributes `diverge`.

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
    predicate: fn(view T) ->{e} Bool captures {..C},
) ->{e} FindSplit<T>
where e: NonAbandoning,
      ..C: Dup + Discard;
```

All input elements remain represented on every recoverable outcome. Similar library families SHOULD cover split/search and fallible fold/traversal patterns. A consuming combinator that can return early while owning arbitrary non-`Discard` state MUST return that state, discharge it structurally, or impose the corresponding `Discard` requirement; this is the same general ownership-preserving failure law as §33.2.

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
fn() ->{e} T captures {...}
```

already expresses a delayed computation with explicit effects and capture/usage semantics.

# Part VII — Structured Concurrency

## 38. Execution domains and strands

### 38.1 Concurrency model

Eldude structured concurrency consists of logical strands scheduled inside an execution domain.

At most one Eldude strand in one execution domain executes Eldude code at a time.

`spawn` therefore means concurrency/interleaving, not simultaneous shared-memory execution.

### 38.2 No implicit preemption

A running strand continues until it reaches an actual semantic suspension point or terminates/exits.

The runtime MUST NOT invisibly preempt ordinary Eldude code at arbitrary instruction, allocation, loop, or call boundaries.

This makes interleaving points part of source-level/effect-level reasoning.

### 38.3 Parallelism

The current language does not specify a general source-level shared-memory parallelism API or memory model. User-directed multicore execution of ordinary Eldude strands is outside the 0.0.2 language scope; programs requiring it must currently use host/native facilities.

No ordinary `Send`, `Sync`, `Transfer`, or thread-affinity predicate exists.

The implementation may use parallel execution internally only when observational equivalence with the specified single-domain semantics is preserved, including effect/defect ordering.

Explicit parallel computation may be designed later as a separate facility if concrete workloads justify it. Such a facility must define its own transfer and state-access boundary rather than retroactively changing ordinary `taskgroup` concurrency into shared-memory parallelism.

## 39. `taskgroup`

### 39.1 Lexical ownership

```eldude
taskgroup {
    let a = spawn fetchA();
    let b = spawn fetchB();
    combine(await a, await b)
}
```

A taskgroup owns every child spawned lexically within its body.

A child cannot be transferred to an unrelated outer lifetime owner by returning its task handle.

### 39.2 Normal completion

When the taskgroup body reaches normal completion, the group waits for all still-running owned children before the taskgroup expression returns.

Completed child results whose handles were discarded are safely discarded because all spawned result types satisfy `Discard`.

### 39.3 Early exit

If the body attempts to leave the group through:

- `return`;
- `?` propagation;
- `break`/`continue` crossing the group;
- affine zero-resumption algebraic control;
- outer cooperative cancellation;
- assertion defect;

then the taskgroup:

1. records the current structural outcome;
2. requests cancellation of all outstanding children;
3. drains children until they terminate, subject to possible `diverge`;
4. allows child `using` cleanup to run under its cancellation-protected rules;
5. propagates the resulting primary outcome after structural shutdown completes.

If a first defect is observed during shutdown while a non-defect outcome was pending, the defect becomes primary and the previous outcome becomes suppressed diagnostic context. If a defect was already primary, later child/cleanup defects are secondary diagnostics. This is the general precedence rule of §20.2.

### 39.4 Structural protection

Once taskgroup shutdown/drain begins, the group itself is not abandoned by another cooperative cancellation delivery. Pending outer cancellation remains pending until the structural shutdown obligation is discharged.

Process destruction or host termination is outside the source-language guarantee.

### 39.5 Child business errors

A child producing:

```eldude
Result::Err(error)
```

has completed normally with a value. This does not automatically cancel siblings or fail the taskgroup.

Only parent control flow such as:

```eldude
let x = await task?;
```

may choose to propagate that error, after which normal taskgroup early-exit shutdown applies.

### 39.6 Child defects

If a child assertion-defects, the group enters structural defective shutdown: siblings are cancellation-requested and drained and cleanup runs. The child defect becomes the primary outcome unless an earlier defect is already primary, in which case it is secondary diagnostic information.

The defect is not converted into `Result` or a task outcome value. A child defect observed while a return, `?`, affine zero-resumption outcome, or cancellation was pending supersedes that non-defect outcome according to §20.2.

## 40. `spawn`

### 40.1 Lexical form

`spawn` is a language form valid only in the immediate executable body of a `taskgroup`, including ordinary nested blocks, branches, loops, and `try` expressions in that body.

A nested function, closure body, handler clause, or separately declared helper does not inherit permission to spawn into the surrounding group's lifetime merely because its declaration text occurs inside the group. Such a nested computation must establish its own `taskgroup` if it needs to spawn children.

```eldude
let task = spawn computation();
```

The operand denotes the child computation itself; it is not first evaluated as an ordinary parent-strand function call. Conceptually it elaborates to an owned zero-argument child closure.

Free values required by the child are captured by ownership according to ordinary usage rules.

### 40.2 No access-grant capture

`view` and `mut` grants never cross a task boundary.

An unrestricted value may be semantically duplicated into the child. A non-`Dup` value captured by the child moves into the child computation.

Aliasable region values such as `Ref<T,@r>` may be shared when their lexical region outlives the whole taskgroup/child lifetime; all execution remains within one cooperative domain.

### 40.3 Spawn result restriction

If the child computation returns `T`, then `spawn` requires:

```text
T: Discard
```

The child may own arbitrary linear/affine resources internally. It must discharge them or transfer them into other valid child-local owners before producing its discardable asynchronous result.

### 40.4 Child cancellation safety

Ownership moved into a child is subject to the same non-local control-exit rules as any other frame. A child that may be cooperatively cancelled while holding a linear resource must have a valid structural discharge path, commonly through `using` or an operation with an explicit cancellation-safe ownership contract.

### 40.5 Spawn itself does not suspend

Creating/registering a child does not by itself switch strands and does not contribute `suspend` to the parent expression solely at the `spawn` site.

Because scheduling is cooperative, the child begins making progress when the current strand next suspends or reaches a taskgroup boundary that must wait for children.

## 41. `Task<T>`

### 41.1 Usage

Every `Task<T>` produced by safe `spawn` satisfies:

```text
T: Discard
Task<T>: Discard
Task<T>: not Dup
```

The handle is a unique observation/cancellation authority, not the owner of child lifetime.

### 41.2 Taskgroup provenance

A task handle retains the fresh lexical taskgroup identity of its creator in compiler-tracked capture/provenance metadata. It also retains the result provenance that `await` may later reveal, including hidden captures described by the child computation's result-capture contract.

Those provenance facts are not user-visible generic parameters. They cannot be erased by containers or `any` packaging, and the group identity cannot escape the group because ordinary capture non-escape checking rejects such a result.

This prevents:

```eldude
let t = taskgroup {
    spawn work()
};
```

and prevents hiding the handle in an outer `Ref`, closure, `any` package, or container that outlives the group.

### 41.3 Discarding a handle

Discarding `Task<T>` has no semantic effect.

The child continues to exist under the taskgroup's ownership. At normal group exit it is awaited/drained; at abnormal group exit it is cancellation-requested and drained.

Discarding a handle is therefore structured fire-and-forget, not detachment.

## 42. `await`

### 42.1 Result

```eldude
await task
```

consumes `Task<T>` and returns exactly `T`.

There is no mandatory `TaskOutcome<T>` wrapper.

A child `Result::Err` remains the ordinary `T` value when `T = Result<E,A>`.

### 42.2 Suspension

`await` admits `suspend` because the current strand may need to yield until the child completes.

If the child is already complete, the particular execution need not actually suspend.

### 42.3 Termination dependency

Awaiting a known-total child does not inherently require `diverge`.

Awaiting a child known to admit nontermination contributes `diverge` through the elaborated control-dependency graph.

Awaiting an opaque task whose producer termination cannot be proved also contributes `diverge` conservatively.

## 43. Cancellation

`cancel()` is a standard `Task<T>` API operation with language-defined structured-concurrency semantics; it is not a separate keyword or core control-form syntax.

### 43.1 Request semantics

```eldude
task.cancel();
```

consumes the task handle and requests cancellation of that child.

It does not wait for child termination and does not itself suspend.

When `cancel()` returns, the only structural guarantee is that the cancellation request has been recorded/issued according to the runtime contract.

### 43.2 Delivery

Cancellation is cooperative. A child observes pending cancellation only when execution actually reaches an ordinary suspension point, except while cancellation is structurally masked by cleanup or taskgroup shutdown.

Every reachable ordinary suspension point MUST be statically legal as a cancellation exit under §62.2. A naked live linear obligation with no valid discharge path across that point therefore makes the program ill-typed; cancellation is not silently disabled because such an obligation happens to be live.

Pure computation, synchronous ordinary calls, and synchronous effect-handler clauses are not implicit cancellation points. There is no separate `cancellable` suspension category.

### 43.3 Completion race

If the child completes before observing the request, its result may simply be discarded. This is sound because spawned `T` is always `Discard`.

### 43.4 No cancellation outcome

After explicit `cancel()`, the handle is consumed and cannot be awaited.

Group-level cancellation causes the current waiting computation to exit structurally; it does not manufacture a `Cancelled` business result for every `await`.

### 43.5 Yield

A standard task-library operation, declared in module `task`, is conceptually equivalent to:

```eldude
pub fn yield() ->{suspend} Unit;
```

provides an explicit cooperative suspension point for compute-bound code that requires responsiveness. Pending cancellation may be delivered there under the ordinary rule in §43.2.

## 44. Effects of concurrent children

### 44.1 Lexical child-effect ownership

A child computation's effects are accounted for by the enclosing lexical `taskgroup`.

They are not stored as a type parameter on `Task<T>`.

If:

```eldude
fetch: fn() ->{net, suspend, diverge} Result<E, Data>
```

then a taskgroup that spawns `fetch()` admits those child effects as part of the whole structured computation, even if the individual task handle is later discarded.

### 44.2 Parent `spawn` expression

The parent `spawn` expression does not semantically perform the child's `net`, `fs`, or other effects at that instant. Those effects occur when the child strand executes.

This distinction is why `Task<T,e>` is unnecessary and would be misleading.

### 44.3 Group suspension

A taskgroup that may create a child admits `suspend`: at minimum, group completion may need to yield so owned children can run/finish even when no explicit `await` remains in the body.

### 44.4 Generic spawning helpers

A helper cannot inject a child into an arbitrary caller's dynamic taskgroup merely because it is called from inside one.

Permission to use `spawn` does not cross a function, closure-body, or handler-clause boundary. A helper or nested callable that creates concurrency therefore creates/owns its own `taskgroup` and returns only after that group has structurally resolved.

This avoids first-class taskgroup capabilities, lifetime parameters, and latent task-effect rows.

## 45. Handler environment of children

### 45.1 Group baseline

When a taskgroup begins, it records the algebraic handler environment that lexically encloses the `taskgroup` construct itself.

A child effect may resolve through a handler in that baseline only when the corresponding active handler frame is `Dup`. Semantically, each child receives its own reusable frame installation for the same lexical effect-instance identity; duplicated captured values follow ordinary `Dup` semantics. Child inheritance MUST NOT create an implicit shared path to a non-`Dup` captured owner.

If a child effect would resolve to a non-`Dup` baseline handler frame, the composition is rejected unless an appropriate handler is explicitly installed inside that child computation. An unconstrained open child effect row is checked conservatively against ambient non-`Dup` handlers because a future instantiation may contain the handled family. Shared mutable handler state, when desired, uses ordinary explicit aliasable state such as `Ref`.

Every child otherwise executes under the permitted baseline environment plus handlers explicitly installed inside the child computation.

### 45.2 Parent-local handlers

A handler entered only by the parent after the taskgroup begins does not become implicit child context merely because `spawn` occurs lexically inside that handler block.

Thus:

```eldude
handle {
    taskgroup {
        spawn work();
    }
} with handler E {
    ...
}
```

applies the lexical `E` handler frame to the whole concurrent subtree, while:

```eldude
taskgroup {
    handle {
        spawn work();
    } with handler E {
        ...
    }
}
```

uses that handler only for the parent's execution of the inner block. The child does not snapshot that transient frame.

To handle only the child:

```eldude
taskgroup {
    spawn handle {
        work()
    } with handler E {
        ...
    };
}
```

### 45.3 Rationale as normative structure

This rule prevents `spawn` from becoming an implicit arbitrary dynamic-context capture operation, ensures the lifetime of inherited handler frames encloses every child using them, and makes handler inheritance obey the same `Dup` law as other values reused across child computations.

## 46. Structured racing

### 46.1 Library, not syntax

Racing is a standard concurrency-library abstraction rather than a language keyword or general public task-handle `select` primitive.

Conceptually:

```eldude
task::race(
    fn() => left(),
    fn() => right(),
)
```

creates a nested taskgroup.

### 46.2 Semantics

A two-branch race:

1. spawns both branch computations in the nested group;
2. suspends until a first branch completion is observed;
3. records that branch result as the winner;
4. requests cancellation of still-running losers;
5. drains the nested taskgroup;
6. returns the winning value after all owned loser work has structurally terminated.

The runtime may use a private primitive to wait for one of several child completions. That primitive is not part of the public language model.

### 46.3 Effects

The effect row of a race is the union of effects that any branch may perform, plus effects of its structured taskgroup/suspension behavior.

Effects already performed by a losing branch are not rolled back.

Racing is not transactional.

### 46.4 Results and defects

`Result::Err` is an ordinary completed branch result and may win.

A child defect triggers ordinary taskgroup defective shutdown rather than becoming a race value.

Branch result types must satisfy `Discard` because they are spawned results.

### 46.5 Ties

When more than one branch has completed before winner observation, the language does not specify a deterministic winner. Code requiring deterministic priority must use a different abstraction.

### 46.6 Standard structured-concurrency combinators

The standard concurrency library SHOULD provide common structured patterns by owning nested taskgroups internally rather than exposing a first-class taskgroup capability. At minimum the design space includes:

- `join2`-style concurrent composition of two child computations;
- `race`;
- timeout combinators built from a work branch and a clock/timer branch;
- bounded concurrent mapping over finite collections.

Representative contracts obey the same core restrictions as direct `spawn`. Names such as `Duration` and `clock` below are representative standard-library/host vocabulary rather than newly fixed core primitives. For example:

The following declarations belong to module `task`; clients call `task::join2` and `task::timeout`.

```eldude
pub fn join2<A, B, !ea, !eb, ..Ca, ..Cb>(
    left: fn() ->{ea} A captures {..Ca},
    right: fn() ->{eb} B captures {..Cb},
) ->{ea, eb, suspend} (A, B)
where A: Discard,
      B: Discard;

pub enum Timeout<T> {
    pub Completed(T),
    pub TimedOut,
}

pub fn timeout<T, !e, ..C>(
    duration: Duration,
    work: fn() ->{e} T captures {..C},
) ->{clock, e, suspend} Timeout<T>
where T: Discard;
```

A bounded concurrent-map combinator may consume arbitrary input elements into children, but every spawned branch result must still satisfy `Discard`; if one callback value is reused across multiple branches, its retained environment must satisfy ordinary `Dup`/`Discard` multiplicity requirements. All such combinators inherit taskgroup effect accounting, cancellation, handler-inheritance, provenance, defect, and drain rules unchanged.

These library operations do not create detached tasks, a public `select` primitive, or a first-class taskgroup lifetime capability.

## 47. No detached tasks or general supervisor primitive in the core

The core language has no operation that detaches a child from its lexical taskgroup.

Long-lived services are structured by an appropriately long-lived outer taskgroup or by host/runtime-owned root scopes whose lifetime is part of the host contract.

A reusable general supervisor API may be designed later, but it must preserve the same ownership/capture principles and cannot extend region-local state past its valid lifetime.

# Part VIII — Host, Unsafe, and Foreign Interoperability

## 48. Host model

### 48.1 One application host

Every executable or embedding configuration selects exactly one host/runtime integration contract.

Host selection is root/build metadata rather than an ordinary Eldude declaration. A package/build system might record this conceptually as:

```text
application-host = cli::standard
```

This notation is illustrative metadata, not Eldude source syntax.

The selected host establishes the outer runtime contract for the executable or embedding environment.

### 48.2 Host responsibilities

A host may define:

- application startup and exported entry points;
- implementations of external services/effects;
- event-loop and scheduler integration;
- runtime allocation services;
- foreign/native adapters;
- process, plugin, or embedding lifecycle;
- root ownership of externally initiated events/tasks;
- defect reporting at the outer diagnostic boundary.

### 48.3 Libraries remain host-independent

Ordinary libraries describe required behavior through types and effect rows rather than accepting or discovering an ambient `Host` value.

For example:

```eldude
fn load(path: Path)
    ->{fs, suspend} Result<IOError, Data>;
```

states the behavior required from whatever application host ultimately supplies the external implementation.

The host is not:

- a capability object automatically passed to functions;
- a hidden capture;
- an object that pure code may inspect;
- a replacement for ordinary effect typing.

### 48.4 Root and embedding contracts

Application and embedding roots carry a root-only host/embedding contract in build/package/embedding metadata. The contract MUST identify scheduler/event integration sufficient to satisfy the runnable-strand progress rule of §69.6. It may additionally state:

- startup/entry-point shape;
- external effect/service implementations supplied by the host;
- finite-return/progress facts for host-driven waits where such facts justify absence of `diverge`;
- native adapter trust metadata;
- root lifecycle ownership.

These facts are not ordinary module requirements and are not propagated through library interfaces.

### 48.5 Root conformance

After ordinary semantic checking succeeds, the selected root contract is checked against the already-typed application/embedding root.

Root conformance is **not** an additional premise for ordinary expression typing. It cannot satisfy a missing trait, erase an effect, alter `Dup`/`Discard`, extend a region/taskgroup lifetime, or authorize an unsafe operation. Failure of root conformance rejects the executable/embedding configuration, not an otherwise valid ordinary library call. The formal judgment is summarized in §58.7.

## 49. Unsafe code

### 49.1 Purpose

`unsafe` marks a static trust boundary where the programmer asserts proof obligations that safe Eldude cannot establish.

It does not create a different dynamic effect category.

### 49.2 Unsafe blocks

Designated unsafe operations require:

```eldude
unsafe {
    ...
}
```

Inside the block, all ordinary checking remains active:

- type checking;
- effect checking;
- `Dup`/`Discard`/linearity;
- capture checking;
- region non-escape;
- call-scoped access checking;
- non-divergence/`diverge` accounting;
- taskgroup structure.

The block grants permission only for operations explicitly classified as unsafe.

### 49.3 Unsafe functions

An unsafe function:

```eldude
unsafe fn f(...) -> ...
```

places documented safety preconditions on its caller that are not fully represented by the safe type system.

Unsafe operations inside the implementation of an `unsafe fn` still require an explicit `unsafe { ... }` block. Declaring the function unsafe does not make its entire body unchecked.

### 49.4 No general effect erasure

Safe surface Eldude has no general operation equivalent to `unsafePerformEffect` that allows arbitrary effectful computation to masquerade as pure computation.

Compiler/runtime intrinsics may exist internally, but their soundness is part of the implementation proof boundary and they are not a general user facility.

## 50. Raw pointers

### 50.1 Types

Raw pointers are:

```eldude
*const T
*mut T
```

They represent machine/foreign pointer values. They are not safe references and do not participate in the safe `view`/`mut` model.

### 50.2 Operations

Dereference, pointer arithmetic outside statically safe wrappers, constructing pointers from arbitrary integers, and equivalent memory operations require `unsafe`.

Raw-pointer validity, alignment, aliasing, pointee lifetime, and thread rules are explicit unsafe proof obligations unless established by a safe wrapper contract.

## 51. No pinning or immovable ordinary values

### 51.1 Movability rule

Every ordinary Eldude value may be physically relocated by the implementation without affecting source semantics.

The language has no:

```text
Pin<T>
Pinned<T>
Unpin
immovable struct
```

or equivalent general type property.

### 51.2 Physical identity belongs to explicit foreign/runtime storage

When native code needs an address that remains stable, the program uses an explicit foreign-storage abstraction rather than changing the movability semantics of ordinary values.

This keeps ordinary value semantics independent of garbage collection, stack movement, compaction, allocation sinking, representation reuse, and future runtime strategies.

## 52. Foreign declarations

### 52.1 Basic form

Conceptually:

```eldude
extern "C" {
    unsafe fn memcpy(
        dst: *mut Byte,
        src: *const Byte,
        size: C::size_t,
    ) -> *mut Byte;
}
```

C variadics, when supported, exist only in foreign declarations.

### 52.2 ABI facts versus semantic contracts

A C header can establish machine-level facts such as:

- symbol names;
- calling convention;
- field offsets/layout;
- scalar representation;
- parameter/result ABI.

A header does not by itself establish Eldude semantic facts such as:

- ownership transfer;
- pointer retention and stable-address requirements;
- callback lifetime;
- callback invocation cardinality (may skip / exactly once / may repeat);
- whether callback delivery may re-enter or overlap native execution;
- thread affinity or delivery domain;
- callback suspension permission and foreign-control-barrier behavior;
- cancellation rendezvous;
- blocking/suspension behavior;
- finite termination;
- defect rendezvous;
- foreign exception/unwind policy;
- deregistration and in-flight callback draining;
- whether an output is initialized on failure;
- whether two pointers may alias.

Those require explicit audited binding metadata or safe wrapper definitions.

### 52.3 Safe foreign declarations

A raw foreign declaration SHOULD be `unsafe` unless its full semantic preconditions are representable and automatically satisfied by every well-typed Eldude call to that declaration.

Safe wrappers may expose ordinary Eldude APIs after discharging the unsafe proof obligations internally.

## 53. Foreign storage and identity

### 53.1 Opaque foreign handle

When native code only needs an opaque token that it will later return to Eldude, the bundled runtime/library may provide a rooting-handle facility conceptually like:

```eldude
ffi::Handle<T>
```

The foreign token has stable identity. The underlying `T` remains an ordinary movable Eldude value. Native copies of the opaque token are aliases to one runtime registration; copying the token does not duplicate ownership of that registration and does not imply `T: Dup`.

Foreign code MUST NOT dereference or infer the address/layout of `T` from the opaque handle. Resolution of the token back to managed state occurs only through the audited runtime/library facility while the registration remains live.

### 53.2 Handle ownership

The conceptual `ffi::Handle<T>` wrapper is a unique owner of the runtime registration/rooting obligation and is not `Dup` by default. The exact type name/API is a runtime-library choice; any safe equivalent must preserve these semantics.

For non-`Discard` `T`, releasing the handle must transfer/recover the `T` value rather than silently discard it.

For `T: Discard`, a safe wrapper may provide explicit cleanup that unregisters the root and discards `T` according to ordinary usage rules.

No cleanup is triggered merely by `Discard`; if the handle requires runtime deregistration, it is non-discardable or must be used under an explicit cleanup protocol.

### 53.3 Stable dereferenceable native allocation

When native code retains and dereferences a pointer, a runtime/library wrapper uses explicit native storage conceptually like:

```eldude
ffi::Box<T>
```

The conceptual abstraction owns one stable native allocation whose address does not change during its lifetime. A wrapper such as `ffi::Box<T>` may itself move as an ordinary Eldude value. The exact wrapper name is not a core-language requirement.

`T` must have a foreign representation contract appropriate to the target ABI. If native storage itself retains references back to movable Eldude-managed values, those references must use opaque rooting handles or another explicitly audited rooting representation rather than raw retained pointers into ordinary movable Eldude storage.

Raw pointer extraction remains unsafe or is exposed only through a narrowly audited scoped API whose contract guarantees the required validity.

### 53.4 Temporary marshalling

When native code promises not to retain a pointer after a call, permanent stable allocation is unnecessary.

Safe wrappers SHOULD prefer scoped marshalling APIs conceptually like:

```eldude
ffi::withBytes(view bytes, fn(native) {
    unsafe {
        c_write(view native.ptr(), view native.len());
    }
});
```

Entering a safe temporary-marshalling callback introduces a fresh compiler-internal foreign provenance identity, conceptually `MarshalProvenance`, whose validity horizon is exactly that callback invocation's dynamic extent. Every safe temporary native-view/token value produced for that scope retains `MarshalProvenance`, and ordinary capture/provenance transitivity applies through closures, containers, dynamic trait packages, task handles, and opaque nominal wrappers.

The callback result and every value escaping the callback invocation MUST NOT retain `MarshalProvenance`. Storing such a value into longer-lived aliasable storage is rejected by the ordinary retention-horizon rule. A nested taskgroup or other structural computation may use the temporary view only when its entire retained lifetime resolves before the marshalling callback returns; the fresh provenance prevents work or results tied to the view from escaping that boundary.

The pointer is therefore valid only for the callback's dynamic extent. The `MarshalProvenance` rule establishes the lifetime horizon of the safe view; it does not by itself prove physical address stability. The marshalling wrapper MUST separately ensure that any dereferenceable native address remains valid for the entire callback invocation, for example because the representation is already stable for that interval, by copying into temporary native storage, or by another audited implementation-private technique. Such implementation machinery does not create a source-level `Pin` property.

Raw-pointer extraction from the temporary view remains unsafe unless a narrower audited scoped operation proves validity automatically. Unsafe code that deliberately retains or exports a raw pointer past the marshalling horizon assumes the corresponding native lifetime proof obligation and is outside safe-language soundness. A safe marshalling wrapper MUST NOT expose a safe result whose correctness depends on such retention.

### 53.5 Native arenas

A general stable native arena is not a core-language primitive. Libraries MAY build scoped native arenas from unsafe/native allocation facilities when a concrete foreign graph/intrusive-data use case requires them.

Such an arena does not become an Eldude region merely because its allocations share a lifetime.

## 54. Strings and buffers at the FFI boundary

### 54.1 Text

`Text` does not implicitly convert to `char*`.

Bindings distinguish:

- bytes plus explicit length;
- NUL-terminated buffers;
- source/target encoding;
- mutable versus immutable buffer access;
- call-scoped versus retained storage.

### 54.2 Mutable buffers

A foreign call mutating an Eldude-owned buffer must have a safe exclusivity/lifetime contract that can be represented by the wrapper. Otherwise raw pointer exposure is unsafe.

A foreign call retaining an Eldude buffer pointer beyond the call requires explicit stable native storage or another audited retention mechanism. Ordinary movable Eldude storage is not implicitly pinned.

## 55. Foreign calls, blocking, and suspension

### 55.1 Contract classification

A foreign operation's binding contract must state enough information to classify it as applicable among:

- synchronous execution with a finite-return contract;
- synchronous execution that may block or otherwise fail to return;
- synchronous execution that may re-enter Eldude through callbacks;
- an offloaded wait that may suspend the calling Eldude strand;
- an asynchronous operation completed by a posted event or equivalent runtime rendezvous;
- an operation whose native cancellation is unsupported, request-only, or completion-confirming.

These facts contribute to the public effect, cancellation, ownership, and non-divergence contract.

### 55.2 Blocking and `diverge`

A synchronous call without a finite-return contract contributes `diverge` even if it does not expose an algebraic effect. Synchronous blocking by itself does not contribute `suspend`: if the execution-domain thread remains inside native code, no other Eldude strand runs merely because the native call is blocked.

### 55.3 Offloaded waits

If the runtime arranges for a foreign operation to complete asynchronously while yielding the Eldude execution domain, its safe wrapper contributes `suspend`. If finite completion of the underlying native operation is not established, the wrapper also contributes `diverge`.

The implementation must preserve the specified foreign-thread/callback, ownership, and shutdown contract while offloading.

### 55.4 Native cancellation

A native cancellation request is not evidence that the native operation has terminated. A request-only cancellation operation does not itself contribute `suspend` merely by issuing the request, but any owner of native resources or retained Eldude provenance MUST remain live until completion, explicit drain, or another contractually sufficient terminal rendezvous. A wait for termination contributes `suspend` when it yields the Eldude strand and contributes `diverge` unless finite termination is justified by the audited contract.

## 56. Callbacks and execution domains

### 56.1 Same-domain synchronous callback

A foreign function may synchronously call back into Eldude on the same execution-domain thread when the audited binding contract permits reentrancy.

The callback contract MUST state invocation cardinality. A callback that may be skipped and abandoned requires a discardable callable environment; a skipped callback may instead be returned/transferred or consumed by an available specified structural-discharge operation under §12.4. One that may be invoked repeatedly requires a duplicable callable environment. The contract also states whether the same callback registration may be re-entered before a prior invocation returns. Re-entry of the same registration requires a duplicable callable environment because two live invocations may overlap. Re-entry through a distinct independently owned registration does not by itself duplicate the first callback value.

Such a callback is nested execution, not a new parallel Eldude strand. Active `view`/`mut` grants in the waiting Eldude/native call chain remain active during synchronous re-entry. The audited aliasing/reentrancy contract and the safe wrapper MUST therefore ensure that a re-entered callback cannot create a grant conflicting with an already active grant to the same mutable owner or native-backed storage.

An ordinary safe same-domain synchronous callback executes beneath an internal **foreign-control barrier** represented in the structural context `Control` (§58.8). Under the ordinary barrier:

- the callback's residual callable contract MUST NOT admit `suspend`;
- execution MUST NOT reach an ordinary suspension point such as `await`, `task::yield()`, a suspending host/foreign wait, or structural cleanup whose residual contract admits `suspend`;
- algebraic handler lookup MUST NOT cross the barrier: every algebraic operation performed by the callback must be interpreted by a handler installed on the callback side of the waiting foreign frame, or the composition is rejected;
- the prohibition on crossing the barrier applies equally to `tail`, `once`, and `affine` operations. `NonAbandoning` is insufficient to relax this rule because `tail` and `once` do not abandon the continuation but may still require continuation capture and resumption;
- pending cooperative cancellation is not delivered through the foreign frame. Because the ordinary callback cannot suspend, a cancellation request remains pending until execution has returned through the foreign call and reaches an ordinary unmasked Eldude suspension point.

A function value whose public effect row admits `suspend` therefore cannot be used directly as an ordinary synchronous callback merely because a particular implementation path is expected not to suspend. Likewise, an opaque callback whose residual row contains an algebraic family must be wrapped so that the family is handled on the callback side of the barrier before callback return. These are separate-compilation rules over canonical callable contracts, not implementation-body inspection.

A safe adapter for a callback that can defect MUST provide a defect rendezvous. At the first transition into defect processing, before callback-local structural discharge or any further native call, the runtime records the defect and marks every active enclosing synchronous foreign invocation in the affected waiting call chain as defect-pending. It then performs callback-local structural unwinding according to the ordinary Eldude rules, prevents normal Eldude continuation of the failed callback, returns through the foreign frame using an ABI-valid private control path guaranteed by the audited native contract, and resumes Eldude defect unwinding only after control reaches an Eldude boundary. Any sentinel/status used solely for this rendezvous is adapter-internal and is not exposed as a normal recoverable application result. If the native API cannot guarantee such a rendezvous, the synchronous callback adapter is unsafe.

Each synchronous foreign invocation has an internal defect-pending state shared by callback entries through that invocation and its nested waiting native call chain. The state MUST be set when the defect first becomes pending, before any callback-local structural unwinding/native call, rather than only when unwinding reaches the barrier. Every active enclosing invocation is marked; after an inner invocation reaches rendezvous, enclosing invocations remain pending until their own Eldude boundaries are regained. Until the invocation reaches its Eldude rendezvous boundary, every further callback entry through the affected invocation MUST be suppressed: it executes no callback body, forms no Eldude grants, and returns only the audited ABI-valid private failure/control result. This applies to another registration as well as re-entry of the failed registration. The contract must make repeated suppressed entries valid for the native caller; otherwise the adapter is unsafe.

Already-required callback-local structural unwinding may continue; it does not authorize fresh normal callback work. Native calls made during that discharge must honor the same pending-state check. Suppression is invocation-scoped, not a domain-wide suspension of unrelated strands or registrations. A pending defect cannot be cleared by native success, callback retry, or returning an ordinary sentinel. At rendezvous the waiting Eldude computation resumes defect unwinding, never normal completion. The retained callback/registration obligations of a suppressed entry remain owned until their specified structural discharge; suppression does not count as a successful callback delivery or silently release roots. The rule also applies to audited stack-preserving protocols.

A host/native adapter MAY define a separately audited **stack-preserving synchronous callback protocol** that permits `suspend`. Such a protocol MUST specify at least native-stack/frame lifetime while parked, the thread/fiber on which resumption occurs, runtime rooting of managed values reachable from the parked computation, stability of retained dereferenceable native pointers, permitted reentrancy, cancellation rendezvous, defect rendezvous, and shutdown behavior. Under such a protocol, suspension uses the ordinary Eldude `suspend` and cancellation semantics; the exceptional protocol does not create a second suspension effect. Permission to suspend does not by itself permit an algebraic operation to target a handler outside the foreign-control barrier. Cross-foreign-frame algebraic continuation capture/resumption is not part of the ordinary safe FFI model in 0.0.2.

### 56.2 Asynchronous callback from another native thread

Arbitrary native threads do not directly execute unrestricted Eldude code.

A safe retained callback arriving from another native thread is converted by the runtime/native shim into an event posted to the appropriate Eldude execution domain. The Eldude callback body executes later under ordinary single-domain scheduling. Posting does not grant the foreign thread an immediate synchronous Eldude result; a native API that requires such a result falls under §56.3 unless a dedicated audited bridge defines the wait and runtime-attachment semantics.

The callback registration must have an explicit structured lifetime owner: a host root scope, a taskgroup-compatible wrapper, or another audited owner. Closing that owner MUST prevent acceptance of new callbacks according to the native contract, deregister the native callback, and drain or otherwise terminally account for already accepted/in-flight callback deliveries before captured Eldude state and rooting registrations are released. If the native API cannot provide a trustworthy lifetime/deregistration boundary, a bounded ordinary safe registration is not available; the callback must instead be owned by an appropriately long-lived host/native root or use an unsafe adapter.

Its audited complete-lifecycle cardinality (§56.2.1) determines the ordinary `Dup`/`Discard` requirements on the retained callback value; repeated delivery requires a duplicable callable environment. Runtime queueing, batching, and backpressure strategy are implementation/library choices, but observable dropping, coalescing, blocking, or bounded-queue failure is part of the adapter's public semantic contract.

### 56.2.1 Lifecycle cardinality and undelivered obligations

A retained callback's cardinality is measured over its complete registration lifecycle, including successful delivery, native cancellation, explicit close, owner cleanup, queue suppression/coalescing, and accepted/in-flight work. The contract MUST distinguish native event occurrence, accepted delivery, and actual invocation of the Eldude callable. An unconditional `exactly once` callable contract means one invocation before every normally completed lifecycle; an API whose close can suppress that invocation cannot advertise that unconditional guarantee.

At registration, ownership of each non-`Dup` callback instance transfers to exactly one lifecycle obligation. Posting transfers responsibility to one accepted delivery; it does not duplicate the registration's obligation. Close races with acceptance/delivery must select one owner and one terminal outcome. Native copies of a token and queue bookkeeping are not additional owned callback instances.

Every path that suppresses an undelivered callback MUST do one of the following, and its public ownership/effect contract must identify which:

- abandon it only when the complete callback environment satisfies `Discard`;
- return or transfer the uninvoked callback as an owned result/obligation, after deregistration and the required accepted/in-flight drain;
- consume it through a specified structural discharge protocol that accounts for every captured obligation. Generic dropping of a non-`Discard` closure is not such a protocol. Safe generic code cannot inspect an opaque function value to recover its captures; the callable representation/interface or an audited intrinsic must actually provide the discharge operation. A documented terminal cancellation invocation may discharge it when the callback signature admits that outcome.

For example, a consuming `cancel` may return `Option<Callback>`: `Some` returns the still-uninvoked instance, and `None` proves that invocation or the advertised structural discharge already owns/completed it. The adapter cannot report `None` merely because the native event was never delivered. A queued but unstarted callback must likewise be drained, recovered, or validly discharged rather than lost when the queue closes.

Canonical `Cleanup` returns `Unit` and therefore cannot use the callback-return alternative. A registration offering automatic close via `using` must require `Discard` for any callback it can abandon, or guarantee invocation/structural discharge during cleanup. Its cleanup row includes all callback/discharge/drain effects that may run, including `suspend` or `diverge` where applicable. A finite-return claim requires the corresponding terminal drain/discharge guarantee.

Once the callback is invoked, its ordinary callable-instance and control-exit rules govern its environment; the registration still owns native deregistration/rooting and drain responsibilities. Cancellation of an in-flight callback is not evidence that those responsibilities ended. Defect exits follow §20's best-effort structural semantics rather than promising normal exactly-once completion; pending-defect suppression (§56.1) never erases a live registration obligation.

### 56.3 Synchronous arbitrary-thread callback

A foreign API requiring Eldude code to execute synchronously on an arbitrary external thread with an immediate return value cannot use the general safe callback mechanism.

Supporting such an API requires a dedicated unsafe/native adapter with explicit runtime attachment, synchronization, rooting, callback-lifetime, and foreign-control semantics.

Eldude does not add `Send`/`Sync`-like predicates to all values merely to support this case.

## 57. Foreign unwinding and failure

Typed Eldude failure and algebraic control MUST NOT unwind through arbitrary foreign frames. Ordinary safe Eldude likewise does not permit a C++ exception, Rust/native unwind, `longjmp`, forced unwind, or equivalent native non-local transfer to skip live Eldude frames. Safe adapters catch, translate, or rendezvous such control at the audited boundary before ordinary Eldude execution continues.

A platform-specific host/native adapter MAY support a stronger cross-language unwind protocol only as an explicit audited trust boundary that preserves the Eldude structural obligations it crosses. Such support is not implied by an ordinary foreign declaration or calling convention and does not alter the portable safe-language semantics.

Safe adapters translate typed results/control outcomes at the boundary.

Assertion defects likewise MUST NOT unwind through arbitrary foreign frames. A safe synchronous callback adapter must use the defect-rendezvous protocol of §56.1 so that Eldude structural unwinding resumes only after the audited foreign call regains an Eldude boundary. If the native call may fail to return after such a callback failure, that possibility contributes `diverge`.

A defect MUST NOT be presented as a normal recoverable C return unless the wrapper deliberately translates it before crossing the ABI boundary as an explicitly different API contract.

# Part IX — Formal Static and Dynamic Semantics

## 58. Static contexts and judgments

### 58.1 Principal judgment

A representative expression judgment is:

```text
TypingEnvironment ; Regions ; Handlers ; Taskgroups ; Usage ; Access ; Control
    ⊢ expression : ResultType ! Effects ▷ Captures
```

The formal semantics deliberately uses descriptive metavariable names rather than single-letter context symbols.

where:

- `TypingEnvironment` maps ordinary names to type schemes and static facts;
- `Regions` contains in-scope generative regions and state schemas;
- `Handlers` contains in-scope algebraic effect-instance/handler evidence;
- `Taskgroups` contains lexical taskgroup identities plus live-child effect and capture/provenance summaries;
- `Usage` tracks affine/linear usage obligations;
- `Access` tracks active call-scoped `view`/`mut` grants, including parent owner/region/projection identity and the supplied state authority of `mut` grants;
- `Control` summarizes enclosing structural/control delimiters needed for continuation-abandonment and foreign-boundary checks and the corresponding structural-discharge machine behavior, including whether cooperative cancellation is currently masked by canonical cleanup or taskgroup shutdown and whether execution is beneath an internal synchronous foreign-control barrier; it is bookkeeping over existing `using`, handler, loop/function, taskgroup, and audited foreign-entry frames, not a new source-language semantic dimension;
- `ResultType` is the result type;
- `Effects` is the admitted effect row;
- `Captures` is the capture/provenance summary of the resulting first-class value when relevant.

A compiler may decompose this judgment internally, but its decisions must be observationally equivalent.

### 58.2 Kinding

Representative judgments include:

```text
StaticEnvironment ⊢ TypeExpression : Type
StaticEnvironment ⊢ Effects : EffectRow
StaticEnvironment ⊢ @region : Region
StaticEnvironment ⊢ Captures : CaptureRow
StaticEnvironment ⊢ NaturalIndex : NatIndex
StaticEnvironment ⊢ Predicate : Constraint
```

`StaticEnvironment` contains the generic binders, kinds, static equalities, and constraints needed to form these categories.

### 58.3 Local generalization

For a local binding `let name = initializer`, first derive monomorphically:

```text
TypingEnvironment ; Regions ; Handlers ; Taskgroups ; Usage ; Access ; Control
    ⊢ initializer : ResultType ! Effects ▷ Captures
```

Let `GeneralizedVariables` be candidate rank-1 variables occurring in `ResultType` that are not fixed by the surrounding contexts. The implicit generalization `name : forall<GeneralizedVariables>. ResultType` is permitted only when:

```text
Effects = {}
GeneralizedVariables ∩ FV(TypingEnvironment, Regions, Handlers, Taskgroups, Usage, Access, Control, Captures) = {}
GeneralizedVariables contains no lexical Region/provenance identity
```

Any effectful initializer is therefore monomorphic at that binding. In particular, creation of aliasable mutable identity has `state<@r>`, so `Ref::new(...)` cannot be generalized into a polymorphic cell. Explicit local `forall` annotations are checked against the same side conditions and cannot override them.

This rule is intentionally conservative. A future relaxation may generalize additional expressions only if it preserves the same mutation/provenance safety and does not make typing depend on implementation heuristics.

### 58.4 Usage predicates

The compiler assigns judgments such as:

```text
StaticEnvironment ⊢ TypeExpression : Dup
StaticEnvironment ⊢ TypeExpression : Discard
```

These are intrinsic semantic predicates, not trait-resolution goals supplied by user `impl` declarations.

Structural derivation MUST preserve the guarantee that duplication/discard of the outer value cannot duplicate/abandon a forbidden inner obligation.

### 58.5 Effect-control predicates

The compiler assigns the intrinsic judgment:

```text
StaticEnvironment ⊢ Effects : NonAbandoning
```

for effect rows whose **ordinary unmasked** continuation-control envelope cannot abandon the surrounding continuation. For a closed row this holds exactly when `mayAbandon(UnmaskedControl, Effects)` from §17.3 is false. For an open row variable `e`, the judgment holds only when the constraint environment contains `e: NonAbandoning`. Generic substitution for such a variable is valid only when the substituted row satisfies the same judgment.

The judgment is compositional over row union: every fixed row entry and every open component must be non-abandoning for the combined row to satisfy it. `NonAbandoning` is compiler-governed and has no user `impl` form.

Static control checking also uses the context-relative helper `mayAbandon(Control, Effects)` from §17.3. Structural masking is represented by `Control`; it may remove the cancellation edge contributed by `suspend`, but it does not grant `NonAbandoning` to the row itself and does not neutralize unknown or explicit algebraic `affine` behavior.

### 58.6 Dynamic-interface judgments

Representative judgments are:

```text
StaticEnvironment ⊢ PackageInterface : DynInterface
StaticEnvironment ; PackageInterface ⊢ Method : DynMethod
```

where `PackageInterface` is an `any Trait<...>` package interface after visible trait arguments and associated-type equalities have been supplied. `StaticEnvironment ⊢ PackageInterface : DynInterface` holds exactly when the package is well-kinded and every trait method satisfies `StaticEnvironment ; PackageInterface ⊢ Method : DynMethod`.

`StaticEnvironment ; PackageInterface ⊢ Method : DynMethod` is the algorithm of §11.2: substitute package-visible trait arguments and ordinary associated types; reject method-local generic parameters, raw `Self` outside the receiver, every GAT projection, unresolved associated projections, constraints not derivable from `PackageInterface`, and any effect/result-capture contract that mentions hidden concrete-type information. The judgment depends only on canonical interface data.

Packaging a concrete value `value: ConcreteType` as `PackageInterface` additionally requires:

- `ConcreteType` satisfies the trait implementation represented by `PackageInterface`;
- the concrete implementation's associated types agree with every equality advertised by `PackageInterface`;
- all advertised `Dup`/`Discard` guarantees hold;
- the package preserves the value's tracked capture/provenance and any mutable-owner status required by the erased interface.

A dynamic method invocation uses the already-substituted public method contract from `PackageInterface`, including its effect row and result-capture transformer. It does not inspect the hidden implementation body or reopen dynamic-compatibility checking at the call site.

### 58.7 Root host/embedding conformance

Root validation uses a separate judgment conceptually:

```text
RootContract ⊢root ApplicationRoot
```

where `ApplicationRoot` is an already well-typed application/embedding root and `RootContract` is the selected root host/embedding contract from §48.4. The judgment checks exactly the root-integration obligations of §48.5: startup/entry compatibility, provision of host-supplied external service/effect implementations, scheduler/event integration including §69.6 runnable-strand progress, any host-driven finite-return assumptions relied on by no-`diverge` contracts, referenced native-adapter trust metadata, and root lifecycle ownership.

`RootContract` is not added to the ordinary expression judgment `TypingEnvironment ; Regions ; Handlers ; Taskgroups ; Usage ; Access ; Control ⊢ ...`. In particular, root conformance supplies no ordinary value, capture, trait evidence, usage permission, region proof, effect erasure, or unsafe permission.

### 58.8 Foreign-control barriers

Entering an ordinary safe same-domain synchronous callback introduces a fresh internal foreign-control barrier `ForeignBarrier` in `Control`. The barrier is non-denotable and is not a source-level value, capability, effect, lifetime, or usage permission.

Conceptually, the ordinary barrier carries the facts:

```text
foreign-sync ForeignBarrier {
    suspend = forbidden
    algebraic-crossing = forbidden
    cancellation-delivery = deferred
    defect = rendezvous
    callback-entry-after-defect = suppressed
}
```

While such a barrier is active:

- an expression or opaque call whose admitted row contains `suspend` is rejected at that execution position;
- effect-instance/handler selection for an algebraic operation may select only a matching handler delimiter installed inside `ForeignBarrier`; if the nearest matching handler lies outside `ForeignBarrier`, the operation/composition is rejected regardless of whether the operation mode is `tail`, `once`, or `affine`;
- `NonAbandoning` does not discharge either check because the barrier concerns foreign-frame participation in suspension and continuation capture, not only continuation abandonment;
- a pending cooperative cancellation request remains pending rather than being delivered through the foreign frame;
- a defect reaching `ForeignBarrier` follows the audited defect-rendezvous protocol of §56.1.

An audited stack-preserving synchronous-callback protocol may replace `suspend = forbidden` with `suspend = permitted` for that specific foreign entry. It must still provide the cancellation/defect rendezvous and lifetime/rooting guarantees required by §56.1. In 0.0.2, such a protocol does not change `algebraic-crossing = forbidden`.

## 59. Function introduction and application

### 59.1 Introduction

Schematic closure typing:

```text
TypingEnvironment, parameters ; Regions ; Handlers ; Taskgroups ; BodyUsage ; BodyAccess ; BodyControl ⊢ body : BodyResultType ! BodyEffects ▷ BodyCaptures
EnvironmentCaptures = tracked outer obligations retained by body
BodyResultCaptureTransformer = inferred relation from EnvironmentCaptures and parameter-value captures (accessed values for access modes) to BodyCaptures
-----------------------------------------------------------------
TypingEnvironment ; Regions ; Handlers ; Taskgroups ; Usage ; Access ; Control ⊢ fn(parameters){body} :
    fn(ParameterTypes...) ->{BodyEffects} BodyResultType captures EnvironmentCaptures [result-capture BodyResultCaptureTransformer] ! {} ▷ EnvironmentCaptures
```

Constructing the closure is pure unless evaluating expressions used to construct an explicit captured object itself performs effects.

`BodyAccess` introduces caller-supplied grants for access-mode parameters. A `mut` parameter is checked under that supplied authority, not as a newly owned root; updates through it follow §14.3 without requiring its type to satisfy `MutableOwner` or name the parent region. Root-grant charges introduced by the body and explicitly declared effects of its calls participate in ordinary effect composition and permitted handler/region elimination to produce the residual `BodyEffects`. Supplied grants and their authority cannot enter `EnvironmentCaptures` or escape in the result. Ordinary values legally copied through them retain their own provenance, which participates in `BodyCaptures` and the result-capture transformer (§13.4).

The callable usage predicates are derived from `EnvironmentCaptures`. `BodyResultCaptureTransformer` is semantic callable metadata and may be omitted from ordinary source rendering while remaining part of the full type/interface contract.

### 59.2 Application consumes one callable instance

For a callable contract conceptually containing:

```text
callable : fn(ParameterModesAndTypes...) ->{CallableEffects} CallResultType captures EnvironmentCaptures
result-capture transformer CallableResultCaptureTransformer
```

application consumes one logical instance of `callable` under the usage environment.

If the binding/value is `Dup`, the checker may semantically duplicate it so the source binding remains usable. If it is affine/linear, the call counts as its consuming use.

Arguments are evaluated left-to-right before establishing call-scoped access grants. The result capture summary is computed from the semantic contract:

```text
ResultCaptures = CallableResultCaptureTransformer(EnvironmentCaptures, Argument1Captures, ..., ArgumentNCaptures)
```

Each `ArgumentNCaptures` is the capture/provenance summary of the supplied argument value; for an access-mode parameter, it is the summary of the accessed value, not of the grant or its authority (§13.4).

If `mayAbandon(Control, CallableEffects)` holds under §17.3, application also checks the relevant enclosing continuation segment(s) in `Control` using the ordinary non-local-exit judgment. For an unconstrained open effect-row variable this check uses the conservative abandoning envelope. Thus an opaque effectful call cannot silently acquire the ability to abandon live non-`Discard` caller obligations.

If `Control` contains an ordinary synchronous foreign-control barrier, application additionally enforces §58.8: a callable whose admitted row contains `suspend` cannot be invoked there, and every residual algebraic family that may be performed by the call must resolve to a handler on the callback side of the barrier. This barrier check is distinct from `mayAbandon` and `NonAbandoning`.

### 59.3 Access modes

For a plain argument or an unprefixed `value.method(...)` receiver, ownership/value semantics apply.

For an explicit `view` argument or `view value.method(...)` receiver, the checker creates a shared non-consuming dynamic-call grant.

For an explicit `mut` argument or `mut value.method(...)` receiver, the checker accepts either (1) a root value satisfying `MutableOwner<T,@r>` for an in-scope region/state schema, or (2) a projected mutable grant already derived from a valid parent owner. It then creates/propagates the exclusive dynamic-call grant and rejects conflicting active access to the same root owner/projection identity.

Forwarding a callee's supplied `mut` parameter likewise propagates its existing grant; it does not require a new `MutableOwner` judgment for the parameter type. Each root grant formed from an owned value contributes its region state to `RootGrantEffects`; forwarding or projection contributes no additional entry solely for granting access. The complete call-expression effects are:

```text
RootGrantEffects = union of {state<@r>} for every root grant formed at this call
CallEffects = CallableEvaluationEffects ∪ ArgumentEvaluationEffects ∪ CallableEffects ∪ RootGrantEffects
```

`CallableEffects` is the invoked callable's declared row, including any explicitly admitted state entries, and MUST NOT be reduced using access authority. Updates through supplied grants use `Access` authority as specified in §14.3. This rule is determined by parameter/receiver modes and preserved grant or mutable-owner provenance, including across dynamic dispatch; imported bodies are not consulted.

For example, forwarding a supplied grant is region-independent:

```eldude
fn invokeMut<T, R, !e, ..C>(
    mut item: T,
    f: fn(mut T) ->{e} R captures {..C},
) ->{e} R {
    f(mut item)
}
```

The helper supplies the existing grant and admits `e`. Calling it with `mut owner` where `owner` is an owned root in `@r` admits `{state<@r>, e}`. Any updates the callback performs through `item` use that supplied authority; its other effects remain in `e`.

The written method-call prefix MUST agree with the selected method's declared receiver mode. These grants do not become values in `TypingEnvironment` and cannot appear in result types/captures.

## 60. Capture soundness

### 60.1 Closure of retained obligations

If a value has capture summary `Captures`, every tracked obligation reachable through that value must be contained in the semantic closure of `Captures`.

The checker may overapproximate. It may not omit an obligation whose omission would permit:

- region escape;
- taskgroup escape;
- illegal duplication/discard;
- escaped lexical effect instance;
- invalid FFI/runtime retention.

### 60.2 Erasure and containers

Nominal containers and `any Trait` packages preserve capture/provenance transitively. Type abstraction cannot erase lifetime/resource provenance required for soundness. Function/method application computes result provenance through the callable's `ResultCaptureTransformer`; erasure does not reset that summary.

Freely aliasable region storage additionally obeys the fixed retention-horizon rule: a write into `Ref<T,@r>` is rejected when the stored value retains any provenance whose validity can end before `@r`.

### 60.3 Scoped foreign provenance

A safe foreign/runtime API may introduce a fresh non-denotable provenance atom with a lexical/dynamic validity horizon. Temporary marshalling (§53.4) is the canonical example. Conceptually, for fresh `MarshalProvenance`:

```text
TypingEnvironment ; ... , MarshalProvenance ⊢ callbackBody : ResultType ! Effects ▷ Captures
MarshalProvenance not retained by Captures
MarshalProvenance not retained by any escaping child/result/runtime registration
---------------------------------------------------------------
TypingEnvironment ; ... ⊢ scopedForeign(callback) : ResultType ! Effects ▷ (Captures \ {MarshalProvenance})
```

Every safe temporary token/view created by that scope carries `MarshalProvenance` in its provenance closure. Ordinary wrapping, dynamic erasure, closure capture, task-result provenance, and aliasable-storage horizon checks preserve it. The scope may end only after all structurally nested work retaining `MarshalProvenance` has resolved and no safe escaping value retains it.

This rule is a use of the existing capture/provenance system. It introduces no source-visible lifetime variable, outlives relation, or pinning property.

## 61. Region typing

### 61.1 Region elimination

Schematic rule:

```text
TypingEnvironment ; Regions,@r ; Handlers ; Taskgroups ; Usage ; Access ; Control ⊢ body : ResultType ! {state<@r>, BodyEffects} ▷ Captures
@r not free in ResultType
@r not retained by Captures
@r not present in any live child/result provenance in Taskgroups or escaping foreign provenance
all @r ownership obligations discharged
-----------------------------------------------------------------
TypingEnvironment ; Regions ; Handlers ; Taskgroups ; Usage ; Access ; Control ⊢ region r { body } : ResultType ! BodyEffects ▷ Captures
```

If the body does not use region state, elimination applies trivially.

### 61.2 `Ref`

Construction of `Ref<T,@r>` requires `T: Discard` and requires every provenance atom retained by the initial payload to outlive or equal the horizon of `@r`.

Reading by value from a still-existing cell requires `T: Dup`. Replacement transfers the old payload and therefore need not duplicate it, but the newly installed payload must satisfy the same retention-horizon condition.

## 62. Usage and control exits

### 62.1 Completed paths

At each completed control-flow boundary:

```text
unrestricted    no exact-use obligation
affine          consumed at most once
linear          consumed exactly once
```

### 62.2 Non-local exit judgment

A non-local exit is legal only if every crossed obligation is either:

- already discharged;
- transferred to the target continuation/result;
- discardable;
- owned by a structural cleanup/taskgroup frame that the exit semantics will discharge.

This common judgment is used for `return`, `?`, loop exits, affine zero-resumption, and cancellation. It is not used to require discharge of arbitrary naked obligations on assertion-defect paths.

At every reachable ordinary suspension point for which `Control` does not mask cooperative cancellation, the checker MUST establish that delivery of pending cancellation would satisfy this same non-local exit judgment. The same check is applied at opaque ordinary calls for which `mayAbandon(Control, Effects)` holds. If it cannot establish legality, the program is rejected. Eldude does not encode a separate cancellability bit or continuation-control permission in source syntax.

A foreign-control barrier is not a structural discharge owner and does not make an otherwise illegal non-local exit legal. Its additional role is prohibitive: under §58.8 it prevents ordinary suspension through, and algebraic continuation capture across, the waiting foreign frame.

### 62.3 Diverging and defect paths

A syntactically diverging path is not treated as if it had consumed arbitrary resources. Runtime responsibility remains governed by cleanup/taskgroup/host contracts. `diverge` records possible nonreturn.

Likewise, a nonrecoverable assertion-defect path is not a completed usage path and is not treated as if it had consumed arbitrary naked resources. Explicit structural owners still perform their specified best-effort defect unwinding; no Eldude continuation may recover a naked obligation after the defect.

### 62.4 Field projection and pattern ownership

For a visible field `field: FieldType` of `AggregateType`, value projection is checked as follows (§8.1):

```text
receiver is an available owned binding or an active access-grant binding to AggregateType
FieldType : Dup
---------------------------------------------------------------
receiver.field : FieldType; receiver ownership/access is preserved
```

A computed owned receiver additionally requires `AggregateType: Discard`; its evaluation effects occur once and its temporary is discarded after projection. The result retains the copied field's capture/provenance summary. Optional field projection applies the same checks to its `Option` receiver (§21.6).

Owned pattern checking consumes the complete matched value and transfers component obligations recursively to subpatterns (§8.4). A name binds the matched owned value; `_` discharges it only when `Discard` holds. Tests and guards inspect before committing those transfers. A pattern checked against an access grant performs no owned transfer or discard: ordinary value bindings require `Dup`, while ignored components remain owned by the caller. No judgment produces a partially moved aggregate or escaping grant.

### 62.5 Usage environments and branch joins

`Usage` is indexed by binding identity, not source spelling; shadowing creates a fresh identity. An owned binding is `Available` until its non-duplicating consuming use, then `Consumed`. A `Dup` use may preserve `Available` by semantic duplication. Uses of a consumed binding are rejected. Branch-local bindings are checked and discharged before they leave scope.

An `if` or `match` checks each alternative from the same incoming environment, after checking the condition/scrutinee once. Only edges that reach the same continuation participate in its join. A `return`, `break`, `continue`, `?`, or affine abandonment edge is checked against its own target; it does not contribute an imaginary state to the expression's normal continuation. Every syntactically present alternative is checked; literal tests do not excuse an invalid ownership path.

For each incoming binding, the normal-continuation join is:

| Incoming ownership kind | Alternative states | Joined state |
|---|---|---|
| Any owned binding, including `using`-owned | All `Available` | `Available` |
| Any owned binding, including `using`-owned | All `Consumed` | `Consumed` |
| Ordinary `Discard` binding | Mix of `Available` and `Consumed` | `Consumed`; the remaining value is discarded on the available edge |
| Ordinary non-`Discard` binding | Mix of `Available` and `Consumed` | Reject |
| Binding owned by an active `using` frame | Mix of live and discharged states | `MaybeLive`, tracked by that cleanup frame |

`MaybeLive` is internal structural-owner state, not ordinary optional ownership. The binding is unavailable to ordinary reads, grants, or consuming uses after the join; its cleanup frame must initiate cleanup on exactly those runtime paths where it is still live. Joins with an existing `MaybeLive` preserve it unless all paths establish discharge. No cleanup effect is introduced by joining an ordinary discardable binding. Other structural owners retain their explicitly specified obligations rather than using ordinary discard to erase them.

The judgment is conceptually `join(Usage1, ..., UsageN) = UsageOut`, with rejection as above; for zero normal edges there is no normal continuation. Available values and branch results retain the union of all possible capture/provenance summaries, with compatible result types and local equalities. Grants introduced within an alternative must end before the join; incoming grants remain subject to the same identity/conflict checks. No branch may restore an ownership obligation consumed on another path.

For a linear `token`, consuming it in only one branch and then continuing is rejected. Consuming it in both branches is valid. A branch that returns after transferring the token may coexist with a continuing branch that still owns it: those edges have different targets and are checked separately.

### 62.6 Loop headers, back-edges, and exits

A loop header has a fixed ownership environment for bindings defined outside the loop. Every continuing back-edge, including explicit `continue` and normal body completion, MUST return those bindings in exactly the header's ownership state. Ordinary immutable shadowing creates a different binding and cannot replace or restore the header obligation. This rule applies to affine as well as linear outer bindings: a continuing iteration cannot consume a value that a later iteration would expect to own.

Loop-local bindings are fresh on each iteration and must be transferred or discharged before every edge leaving that iteration. Structural scopes crossed by `continue` perform their specified discharge before the back-edge is checked. Existing access grants remain valid only for their enclosing dynamic call; a back-edge cannot extend a locally introduced grant.

For `while`, the condition is checked at the header on every iteration. Its true edge feeds the body and its false edge is an ordinary loop exit. For `for`, source evaluation/iterator acquisition occurs once before the header. Each successful `next` introduces a fresh item and the returned remainder; the remainder is the protocol's explicitly threaded loop owner, whose type/usage and tracked provenance contract must be preserved on every continuing edge (§35). This internal iterator replacement does not add source assignment or implicit replacement of outer bindings. The iteration pattern obeys §8.4, including `Discard` for ignored owned items.

After checking back-edges, all condition-false/iterator-completion exits and all `break` exits targeting this loop are joined by §62.5. A possibly zero-iteration loop includes its zero-iteration exit. `break` has no value and does not restore consumed bindings. Early exit with a live iterator remainder remains subject to §35.3. A loop with no normal exit contributes no state to the following continuation; possible `diverge` or defects do not erase obligations on paths that do continue.

Termination/progress checking (§19) is independent of these ownership checks. A decreasing measure cannot justify an incompatible usage back-edge.

## 63. Cleanup typing

### 63.1 `Cleanup` implementation checks

For:

```eldude
impl Cleanup<e> for T
```

the compiler checks:

- `T` is not `Dup`;
- the method consumes `self`;
- result type is `Unit`;
- effects are contained in `e`;
- evaluating `e` under the canonical cleanup structural control context `CleanupControl` satisfies `mayAbandon(CleanupControl, e) = false` under §17.3; equivalently, the cleanup mask may neutralize the cancellation edge of `suspend` but no escaping `affine` family may remain; an affine operation may choose zero resumptions and therefore cannot be part of the residual cleanup contract;
- implementation coherence holds.

### 63.2 `using` typing

Each acquired binding is registered in a cleanup frame with its canonical cleanup row.

The effect row of a `using` expression includes:

- acquisition effects;
- body effects;
- cleanup effects that may execute on any possible exit path.

Cleanup remains conservative in the public row even when some path explicitly consumes a resource before scope exit.

### 63.3 Cleanup and continuations

A cleanup frame is an ordinary structural control/resource obligation for continuation-abandonment analysis. An algebraic operation inside cleanup is checked by the same captured-segment rules as any other operation.

## 64. Algebraic operation and handler typing

### 64.1 Direct operation

For an operation `operation` in effect family `EffectFamily` returning `OperationResult` and selected instance `EffectInstance`:

```text
arguments well typed
EffectInstance : EffectFamily selected
------------------------------------------------
!EffectFamily::operation(arguments) : OperationResult ! {EffectFamily@EffectInstance}
```

If the selected operation mode is `affine`, the checker also identifies the captured segment from the operation to the matching handler delimiter and requires that possible zero-resumption abandonment be a legal non-local exit before accepting the operation site. This check depends on the declaration mode, not on inspecting a particular handler body.

If `Control` contains a synchronous foreign-control barrier between the operation site and the otherwise selected handler delimiter, the operation is rejected before the mode-specific continuation rule is applied. This is true for `tail`, `once`, and `affine`: an arbitrary waiting foreign frame is not part of an Eldude delimited continuation merely because the operation is non-abandoning.

An `affine` operation returning `Never` is treated by the same ordinary affine rule when its handler is reachable without crossing a foreign-control barrier; safe code cannot take its resuming path because it cannot supply a `Never` value.

Source interfaces normally display families rather than elaborated instance identities.

### 64.2 Lexical handler application

Consider:

```eldude
handle {
    body
} with handler EffectFamily {
    clauses
}
```

or the named-instance form:

```eldude
handle {
    body
} with EffectInstance = handler EffectFamily {
    clauses
}
```

The compiler infers for the inline handler block:

- handled family `EffectFamily`;
- body input type `HandlerInputType`;
- `handle` expression output type `HandlerOutputType`;
- complete residual effect row `ResidualEffects`;
- retained frame captures/provenance `HandlerCaptures`;
- result-capture transformer for the `handle` expression.

If the handled body has:

```text
HandlerInputType ! {EffectFamily@EffectInstance, HandlerBodyEffects}
```

then the handled result has type/effect approximately:

```text
HandlerOutputType ! join(HandlerBodyEffects with intercepted EffectFamily@EffectInstance removed, ResidualEffects)
```

where `ResidualEffects` already includes forwarded `EffectFamily` when forwarding is possible.

Intrinsic `diverge`, `suspend`, and region state effects are not removed merely because an algebraic family is handled.

Installing the lexical handler transfers `HandlerCaptures` into one linear handler-frame usage state. The `handle` expression's output capture summary is computed from `HandlerCaptures`, the handled computation's result captures, and clause-produced values. Deep clause re-entry references this same logical frame state; it does not duplicate it.

At `resume(value)`, the static usage transition splits the frame environment by `Dup`: every non-`Dup` frame binding is consumed from the clause-side usage environment and transferred into the resumed computation, while `Dup` bindings may remain available on both sides by ordinary semantic duplication. If the resumption returns, its `HandlerOutput` returns to the clause but transferred non-`Dup` frame bindings do not. The resumed computation is responsible for the ordinary usage/discharge of those transferred obligations. Zero-resumption affine paths retain their frame state locally and must satisfy terminal discharge themselves.

### 64.3 Resumption capability

Inside a resumable clause, the checker introduces an internal non-denotable capability conceptually:

```text
Resume<mode, OperationResult, HandlerOutput, FrameUsage>
```

`FrameUsage` is compiler bookkeeping for the ordinary usage state transferred by §23.3/§64.2; it is not a source-level ownership mode or denotable type parameter. Source code accesses the capability only through `resume(value)`.

The capability cannot escape the clause.

## 65. Captured continuation segment

### 65.1 Segment definition

For an algebraic operation, the captured segment is exactly the dynamic sequence of frames between the operation site and the matching handler delimiter.

Frames outside the delimiter are not part of the captured segment and are not abandoned by zero-resumption at that delimiter.

### 65.2 Structural model

For static abandonment safety, the compiler models the captured segment as an internal structural value containing:

- live owned locals;
- active call-scoped access grants;
- cleanup frames;
- taskgroup control frames;
- nested handler/control frames;
- relevant captures/provenance.

### 65.3 Mode checks

`tail` and `once` require exactly one resumption and therefore do not abandon the captured segment.

`affine` permits zero resumption only when abandonment of the segment is a valid non-local exit. An `affine` operation returning `Never` cannot resume in safe code but uses the same rule rather than a separate mode.

The same abandonment model is invoked indirectly at an ordinary call when the call's derived continuation-control envelope is potentially abandoning. Many-shot continuation duplication is not part of the 0.0.2 core.

## 66. Error typing

### 66.1 `?`

If:

```text
expression : Result<ErrorType, SuccessType>
```

then `expression?` has local success type `SuccessType` and an error-propagation edge carrying the same nominal `ErrorType` to the nearest `try` or enclosing function result.

The target error type must be exactly `ErrorType` after any explicit mapping already performed by source code. No structural injection, widening, trait conversion, or arbitrary function conversion is considered by `?`.

### 66.2 `try`

If every `?` edge inside a `try` block carries the same nominal `ErrorType` after explicit mapping, and normal completion has type `SuccessType`, the result is:

```text
Result<ErrorType, SuccessType>
```

A `try` block whose propagation edges have incompatible nominal error types is rejected until the program maps them explicitly to one chosen type.

## 67. Task typing

### 67.1 Taskgroup context

Entering `taskgroup` introduces a fresh internal group identity `TaskgroupId` in `Taskgroups` and records the handler environment existing at the group delimiter.

### 67.2 Spawn

If `childExpression` has:

```text
childExpression : ChildResultType ! ChildEffects ▷ ChildCaptures
ChildResultType : Discard
```

and the spawn site is in the immediate executable body of the current taskgroup rather than across a nested callable/handler boundary, then `spawn childExpression`:

- registers `ChildEffects` in the enclosing group's child-effect summary;
- registers the child's retained free-value provenance and anticipated result provenance `ChildCaptures` in the group's live-child provenance summary until child/result structural lifetime ends;
- transfers/duplicates free captured values into the child according to usage;
- rejects retained `view`/`mut` grants;
- for each child effect that would resolve through a handler in the taskgroup baseline, requires that active handler frame to be `Dup`;
- produces `Task<ChildResultType>` carrying group provenance `TaskgroupId` together with the child result provenance `ChildCaptures` that a later `await` may reveal;
- does not itself perform `ChildEffects` in the parent strand;
- does not itself add `suspend` merely by child creation.

The enclosing `taskgroup` expression includes child effects and admits `suspend` when it may own any child.

### 67.3 Task provenance non-escape

A result/capture leaving the group may not retain `TaskgroupId`.

This rule rejects escaping task handles transitively through containers, closures, regions, or `any` packages.

### 67.4 Await

`await task` for `task: Task<TaskResultType>` consumes the handle, adds `suspend`, returns `TaskResultType` with the child result-capture/provenance summary carried by the handle, and adds a control-dependency edge to that child's completion.

If the completion dependency is not proved terminating, `diverge` is admitted.

### 67.5 Cancel

`task.cancel()` consumes the handle, records a cancellation request, and does not by itself add `suspend`.

### 67.6 Handle discard

Discarding the handle performs no task action. Group ownership remains unchanged.

## 68. Taskgroup dynamic obligations

### 68.1 Normal exit

A group cannot return normally until every owned child has terminated.

If necessary, the parent strand suspends at the group boundary to permit child progress.

### 68.2 Abnormal exit

On an abnormal exit, the group requests cancellation of outstanding children and drains them before propagating the original control result.

A child that never reaches a cancellation point may cause the shutdown to diverge; non-divergence analysis must account for that dependency.

### 68.3 Defect

A child defect transitions the group into defective shutdown. If no defect is already primary, it supersedes any pending non-defect group outcome; otherwise it is recorded as a secondary defect. It is not turned into a typed child result.

## 69. Dynamic machine

### 69.1 State

Eldude may be modeled by a small-step machine conceptually containing:

```text
⟨ expression,
  lexical environment,
  region stores,
  algebraic handler stack,
  usage/resource state,
  active access grants,
  taskgroup tree,
  runnable/suspended strands,
  pending cancellation,
  host interface ⟩
```

A conforming implementation need not use this literal representation.

### 69.2 Evaluation order

Expressions reduce according to strict left-to-right evaluation, except special forms whose semantics explicitly create delayed child computation (`spawn`) or conditional evaluation (`??`, optional invocation, branches).

### 69.3 Call-scoped access

Access grants are established after ordinary argument evaluation and last until the invoked call frame is discharged, including across algebraic handler suspension.

### 69.4 Regions

Entering a region creates a fresh abstract state identity. Region exit becomes observable only after all static/runtime obligations are satisfied and no safe escaping value, live taskgroup-owned child/result, or retained runtime object keeps the identity validly reachable.

### 69.5 Effects and handlers

A direct algebraic operation captures its delimited continuation to the matching instance handler, subject to the declared resumption mode and static captured-segment safety.

Deep resumption reinstalls the same handler around the continuation.

### 69.6 Cooperative scheduler

A runnable strand executes until an actual suspension point or termination. The scheduler selects another runnable strand only then.

Scheduling itself is not an admitted source of nontermination. When the current strand suspends/terminates and at least one Eldude strand in the same execution domain is runnable, the abstract machine MUST take a scheduler transition selecting some runnable strand rather than stuttering indefinitely in scheduler state. The implementation may choose any runnable strand.

This is a minimal runnable-strand progress property, not a fairness, priority, latency, or bounded-response guarantee. Eldude does not promise that every continuously runnable strand receives service within a time bound or before another runnable strand. Delays caused by external events, host services, foreign completion, locks/protocols outside the language model, or other non-runnable dependencies remain governed by their declared finite-return contracts and admit `diverge` when termination is not justified.

The root host/runtime contract MUST implement scheduler/event integration consistently with this rule. A host cannot preserve a no-`diverge` Eldude contract while introducing unmodelled indefinite starvation of runnable Eldude work.

### 69.7 Cancellation

A cancellation request marks the target strand/group state. Delivery occurs when execution reaches an ordinary suspension point unless cancellation is currently structurally protected by cleanup or taskgroup shutdown. Static typing guarantees that every such unmasked suspension point is a legal cancellation structural exit.

### 69.8 Defect unwinding

Assertion defect initiates best-effort structural unwinding rather than a recoverable control effect. Cleanup/taskgroup obligations execute according to their rules and the primary/secondary defect precedence of §20.2 before the defect reaches the host boundary, unless progress is prevented by divergence or process-level termination. Naked linear obligations are not required to have an Eldude-level discharge path because no Eldude continuation survives the defect.

### 69.9 Foreign callback boundaries

Entering an ordinary same-domain synchronous callback pushes the internal foreign-control barrier of §58.8. The callback executes as nested Eldude execution on the same domain and returns to the waiting native frame only by ordinary callback return or by the audited private defect-rendezvous path.

Under the ordinary barrier, execution cannot take an Eldude suspension transition. A pending cancellation request is therefore retained in machine state until control returns through the foreign call and a later ordinary unmasked suspension point is reached. Algebraic operation dispatch cannot select a handler outside the barrier.

Every callback-entry transition first checks the enclosing synchronous invocation chain for a pending defect. If one exists, the shim takes only the private suppression transition of §56.1; it does not enter Eldude.

At the first defect-processing transition, the runtime records the defect and marks every active enclosing synchronous invocation pending before any callback-local discharge or native call. Callback-local structural unwinding then proceeds while possible; the barrier returns through the native frame using the audited rendezvous protocol, and outer Eldude defect unwinding resumes only when the corresponding Eldude boundary is regained. Removing an inner rendezvoused frame does not clear enclosing pending states. Native non-local unwinding across live Eldude frames is not part of ordinary safe-machine execution.

An audited stack-preserving callback protocol may permit suspension by preserving the waiting native execution state and all required roots/lifetimes. Resumption must re-enter the same logical callback computation according to that protocol. Such an implementation remains subject to ordinary Eldude cancellation semantics at the permitted suspension point and still does not permit algebraic handler lookup across the foreign-control barrier in 0.0.2.

## 70. Soundness obligations

A conforming safe implementation must uphold at least the following properties.

### 70.1 Type preservation

A well-typed reduction preserves type correctness and the admitted semantic contract of the expression.

### 70.2 Progress

A closed well-typed expression is a value, can take a semantic step, is suspended on an admitted operation/wait, is undergoing specified structural shutdown, or has reached an explicit defect/host boundary. It does not become stuck because a safe-language invariant was omitted.

### 70.3 Effect safety

A computation cannot perform an unadmitted ordinary effect, modulo the semantics of handler interpretation and canonical effect weakening. Updates through a supplied `mut` grant are admitted by its explicit access contract and state authority (§14.3); the root invocation MUST account for that authority's region state. This does not admit independent state effects or permit removing an explicitly declared effect from a call's row.

### 70.4 Region safety

Safe code cannot observe region-local mutable identity after the region ends.

### 70.5 Access safety

A call-scoped access grant cannot escape as a first-class value, and conflicting active `mut`/shared grants to the same mutable owner are rejected.

### 70.6 Usage safety

Safe code cannot:

- duplicate a non-`Dup` value;
- discard a non-`Discard` value;
- complete a normal or recoverably transferred control-flow path with a live linear obligation lacking a valid owner/discharge;
- invoke a linear callable twice.

A nonrecoverable assertion-defect path is not such a completed/recoverable path; deterministic resource discharge on defects requires explicit structural ownership.

### 70.7 Capture safety

A first-class value cannot erase retention information needed to enforce region, taskgroup, effect-instance, foreign, or resource lifetime boundaries.

### 70.8 Handler-control safety

Resumptions obey their declared mode and remain lexical. Affine zero-resumption cannot abandon a captured segment whose ordinary usage/control-exit obligations prohibit that action. An active handler frame has one usage state: returning resumptions move every non-`Dup` frame capture into the resumed computation and never restore that ownership to post-resume clause code. Consequently no deep re-entry, return clause, or outer resumable clause can duplicate or double-discharge a non-`Dup` frame capture.

### 70.9 Structured-concurrency safety

No safe spawned child outlives its owning taskgroup, and no task handle escapes its group provenance.

### 70.10 Cleanup safety

Discard alone performs no cleanup effect. `using` initiates canonical cleanup for still-live owned resources on every specified structural exit, with cancellation protection. No residual algebraic effect capable of abandoning the cleanup continuation may escape a `Cleanup` invocation, and cleanup defects follow the general structural-discharge precedence rules of §20.2.

### 70.11 Trait coherence

For the admitted fragment of §§10.6–10.8, implicit trait resolution and associated/GAT normalization are unique, terminating, and independent of import order. Matching, overlap, prerequisite decrease, and opaque-projection equality are defined language rules, not implementation-selected acceptance criteria.

### 70.12 Non-divergence

When `diverge` is absent, the compiler/runtime contracts justify absence of admitted nontermination under all relevant primitive, handler, host, task-dependency, scheduler-progress, and foreign assumptions. The scheduler-progress premise is the minimal no-stuttering rule of §69.6; it is not a general fairness theorem. Normal return is not guaranteed in the presence of an explicit assertion defect or externally delivered structural cancellation; those remain separate nonrecoverable/structural outcomes rather than `diverge`.

### 70.13 Foreign-boundary control safety

An ordinary safe same-domain synchronous callback cannot suspend through an arbitrary waiting foreign frame and cannot capture/resume an Eldude algebraic continuation whose matching handler lies outside that foreign-control barrier. Eldude defects do not unwind arbitrarily through foreign frames, and arbitrary foreign threads do not directly execute unrestricted Eldude code. Any stronger stack-preserving, thread-attachment, or cross-language unwind behavior is confined to an explicitly audited host/native trust boundary and does not silently weaken these portable guarantees.

# Part X — Separate Compilation, ABI, and Tooling

## 71. Separate compilation

### 71.1 Semantic boundary

An ordinary module MUST be semantically checkable from exactly:

- its own source; and
- canonical semantic interfaces of its direct imports.

Imported implementation bodies MUST NOT be required for ordinary name resolution, type checking, effect checking, capture checking, usage checking, trait resolution, non-divergence checking, or region checking. An application or embedding root is additionally subject to the separate root-conformance judgment of §58.7; that judgment does not alter the semantic validity of imported ordinary library modules.

### 71.2 Private implementation stability

A private implementation change that preserves the canonical semantic interface MUST NOT require downstream semantic rechecking.

A compiler may choose to invalidate downstream optimization products, but that is a separate dependency class.

### 71.3 Dependency classes

Tooling SHOULD distinguish at least:

- semantic interface dependencies;
- optimization/inlining dependencies;
- ABI/layout dependencies;
- generated-binding dependencies;
- host/native trust dependencies.

A change in one class does not automatically invalidate every other class.

## 72. Canonical semantic interfaces

### 72.1 Completeness principle

If a fact can change whether downstream source is semantically valid, that fact belongs in the canonical interface.

The interface must be sufficient for downstream checking without implementation inspection.

### 72.2 Required categories

Canonical interfaces contain, as applicable:

- exported names and namespaces;
- nominal type identities;
- visible struct fields/enum constructors;
- opacity markers for hidden representations;
- kinds and generic parameter categories;
- function and method types;
- effect rows plus canonical effect-family control summaries sufficient to derive continuation-control envelopes without requiring transitive implementation inspection;
- constraints on effect-row parameters, including intrinsic `NonAbandoning` constraints;
- callable-environment captures, result-capture transformers, and capture-row parameters;
- intrinsic `Dup` and `Discard` guarantees;
- intrinsic mutable-owner status where applicable;
- region parameters and provenance relations;
- compile-time natural parameters and constraints;
- trait declarations;
- associated types and GAT signatures;
- trait/package declarations sufficient to decide the closed `DynCompatible` judgment for every exported `any Trait<...>` interface;
- implicit implementation headers owned by the module;
- intrinsic `Cleanup` implementation headers and cleanup rows;
- public FFI ABI and semantic contracts;
- explicitly exported layout/ABI facts where representation is part of the contract.

### 72.3 Opaque types

When a module exports an opaque nominal type, clients need not know its fields/layout unless ABI is explicitly exposed.

The interface must nevertheless export client-relevant semantic properties such as:

```text
Dup?
Discard?
implemented traits
Cleanup?
method effects
capture/provenance parameters
result-capture relationships
finite positive storage parameter profiles when exported
mutable-owner status when exported
```

These facts are contracts, not implementation details.

### 72.4 Trait implementation index

Because implicit implementations are owned by the module defining the trait or nominal head type, the relevant module interface can export the canonical implementation headers needed for deterministic resolution.

The index MUST include canonical implementation heads, complete prerequisites, and associated/GAT equations needed by §§10.6–10.8, including dependencies required to interpret those headers. Method bodies are not consulted. Imported headers obey the same admissibility and overlap rules as local headers.

Import order MUST NOT create or remove an applicable implicit implementation.

### 72.5 Handler effects require no standalone interface object

Because handlers are lexical rather than first-class values, canonical interfaces contain no standalone `Handler<...>` value/type contracts.

A public function or method that installs a handler exports its ordinary function contract:

- parameter/result types;
- complete residual effect row after the handler has interpreted its family;
- captures/provenance and result-capture relationships;
- any `NonAbandoning` or other ordinary constraints.

Forwarding behavior relevant to clients is represented by that residual effect row. Downstream checking never inspects handler clause bodies.

### 72.6 Cleanup interfaces

A public nominal type implementing `Cleanup` exports:

- the fact that canonical cleanup exists;
- the cleanup effect row;
- the intrinsic non-`Dup` requirement already implied/verified.

The cleanup body is not a semantic dependency of clients.

### 72.7 Human-readable semantic interface rendering

Every client-validity fact in the canonical semantic interface MUST have a deterministic human-readable rendering produced by the standard toolchain. Facts already expressible in ordinary Eldude syntax use that syntax. Client-relevant inferred facts that have no ordinary author-written spelling use a generated `semantic { ... }` block rather than opaque solver variables.

Representative generated clauses are:

```text
semantic {
    result-captures <= {captures(cell), ..C, @r};
    mutable-owner-region = @r;
    finite-positive-parameters = {0, 1};
}
```

`result-captures <= {...}` is the normalized upper-bound notation of §13.6. `mutable-owner-region = @r` states the intrinsic `MutableOwner<T,@r>` fact when clients may form root `mut` grants. `finite-positive-parameters` lists the zero-based generic parameter positions certified by §8.5; `{}` certifies no positions. FFI facts use the generated contracts and protocol descriptions of §72.9. Other future generated clauses MUST use source-level semantic terminology and MUST NOT expose implementation-specific solver state as the only representation of a client-relevant fact.

A semantic block is attached to its preceding declaration. Nested `member(path) { ... }` clauses select individual methods, fields, associated declarations, or enum constructors by canonical identity; this includes trait and implementation methods and declarations in an `extern` block. Nested `parameter(n)`, `result`, and `component(n)` clauses select callable slots and stored tuple/payload components with the same zero-based rules as §72.9. All semantic clauses, including `result-captures`, may occur at the selected subject. Repeated selectors or facts in the same scope, invalid member/slot identities, or facts inappropriate to that subject are interface errors. Selectors use §72.9's canonical recursive ordering.

Within a selected callable contract, `captures(x)` refers to the named parameter/accessed-value summary. The positional spelling `captures(parameter(n))` refers to its zero-based parameter summary (counting a receiver), and `captures(..)` refers to the callable environment. These spellings make nested anonymous function contracts renderable without inventing author-visible argument names; canonical rendering uses positional spelling for unnamed slots. The bound's meaning and transitive provenance rules remain those of §13.6.

Generated semantic clauses are interface/diagnostic notation. They belong to the canonical-interface grammar of Appendix F, not to the ordinary Eldude source grammar. A generated interface is therefore not promised to be a copy-pastable source stub unless those interface-only clauses are omitted. Tools MUST label/render canonical interface output distinctly enough that interface-only syntax is not presented as ordinary author-written source.

These clauses do not create new user-denotable values, lifetime inequalities, capabilities, or author-written requirements.

### 72.8 Canonicalization and hashing

Interfaces SHOULD have a deterministic canonical serialization suitable for content hashing.

Equivalent public semantics should produce the same semantic interface representation independent of private declaration order or source formatting.

### 72.9 Generated FFI semantic contracts

Every client-relevant audited native fact required by §74.4 MUST appear in a generated `ffi-contract { ... }` inside the declaration's `semantic { ... }` block. Ordinary types, effects, captures, and `Cleanup` remain part of the interface; the FFI clauses record the additional audited obligations and guarantees. These clauses are interface-only notation, never author-written source annotations. Mechanically derived symbol/calling-convention/layout facts remain in the separate ABI representation of §74.2.

A contract describes its attached declaration. `parameter(n) { ... }` selects zero-based callable parameter position, counting a receiver when present; `result { ... }` selects its result. `member(path) { ... }` selects a member by canonical identity, including a function in an `extern` block, a method/field, or an enum constructor/record-payload field of an exported nominal declaration. `component(n) { ... }` selects a zero-based stored tuple or positional constructor-payload component; selecting an enum constructor with `member` first distinguishes its payload from other variants. These selectors may nest to locate contracts on callback arguments/results or aggregate members. Within a selected subject, `pointer`, `output`, `callback`, and `marshalling` blocks distinguish the following applicable facts. Source parameter names are display labels, not contract identities.

The following vocabulary is normative. Values in the table are bare generated words, except capture bounds and `protocol(path)` references. `not_applicable` is permitted only when the fact genuinely does not apply; it is not an unknown guarantee. Unknown/unproved facts MUST be rendered as `unverified` where admitted or as an explicit unsafe precondition described by a protocol, rather than omitted to suggest safety.

| Subject | Keys, in canonical order | Values/meaning |
|---|---|---|
| Callable/native operation | `invocation` | `synchronous`, `offloaded`, `posted` |
| Callable/native operation | `blocking` | `none`, `may_block` |
| Callable/native operation | `finite-return` | `guaranteed`, `unverified`; the latter contributes `diverge` under §55 |
| Callable/native operation | `native-cancellation` | `unsupported`, `request_only`, `completion_confirming`, or `protocol(path)` |
| Callable/native operation | `foreign-unwind` | `no_unwind`, `contained`, or `protocol(path)`; `contained` means caught by the shim without unwinding across live Eldude frames |
| Pointer | `ownership` | `borrowed`, `transferred_to_native`, `transferred_to_eldude`, or `protocol(path)` |
| Pointer | `retention` | `call_scoped`, `retained`, or `protocol(path)` |
| Pointer | `mutability` | `read_only`, `write_only`, `read_write` |
| Pointer | `aliasing` | `exclusive`, `shared_read`, `may_alias`, or `protocol(path)`; these do not remove ordinary access-conflict rules |
| Pointer or marshalling | `stable-address` | `required`, `not_required`; the implementation must establish any required stability |
| Pointer or marshalling | `provenance` | a normalized capture bound, `fresh_scoped`, or `protocol(path)` |
| Output | `initialization` | `always`, `on_success`, or `protocol(path)` |
| Output | `failure-state` | `initialized`, `uninitialized`, or `protocol(path)` |
| Callback or marshalling | `lifetime` | callback: `call_scoped`, `registration`, `root`, or `protocol(path)`; temporary marshalling: `callback_scoped` |
| Callback | `cardinality` | `may_skip` (zero or one), `exactly_once` (one), `may_repeat` (zero or more), or `protocol(path)` for other minimum/maximum or conditional bounds; measured over the complete lifecycle (§56.2.1) |
| Callback | `reentrancy` | `forbidden`, `permitted`, or `protocol(path)`; permission is per registration |
| Callback | `thread-affinity` | `same_domain_thread`, `posted_to_domain`, `audited_attached_thread`, or `protocol(path)` |
| Callback | `delivery-domain` | `current_domain`, `registration_domain`, or `protocol(path)` |
| Callback | `barrier` | `ordinary`, `stack_preserving`, `not_applicable`; `stack_preserving` requires the complete audited §56.1 protocol |
| Callback | `suspension` | `forbidden`, `permitted`; permission does not authorize crossing an ordinary barrier |
| Callback | `algebraic-crossing` | `forbidden` in 0.0.2 |
| Callback | `cancellation` | `deferred`, `ordinary_points`, or `protocol(path)` |
| Callback | `defect` | `rendezvous` or `protocol(path)` describing the applicable Eldude-boundary/private-ABI protocol |
| Callback | `pending-defect-entry` | `suppressed` for synchronous entry; `not_applicable` for independently posted delivery |
| Callback | `deregistration`, `drain` | each `not_applicable` or `protocol(path)` specifying the prevention-of-acceptance and accepted/in-flight terminal obligations |
| Callback | `undelivered` | `discard`, `return_obligation`, `structural_discharge`, `not_applicable`, or `protocol(path)` covering the possible lifecycle outcomes of §56.2.1 |
| Callback or lifetime owner | `shutdown` | `not_applicable` or `protocol(path)` |
| Any subject | `preconditions` | `protocol(path)` for additional audited validity, representation, encoding, lifetime, thread, or unsafe obligations |

Every applicable key MUST be emitted, including conservative ordinary-barrier facts. In addition to the listed scalar values, every key except the fixed `algebraic-crossing = forbidden` permits `protocol(path)` to describe compound/conditional behavior. The protocol MUST enumerate the alternatives and their guards/selection conditions; each alternative obeys the unconditional safe-language laws of §§53–56. This covers a callable that invokes inline on one path and posts/offloads on another, including the corresponding barrier, suspension, and pending-entry modes. It must not choose one scalar outcome that hides another. A protocol may supplement a fixed enum via `preconditions`; it cannot contradict that enum or relax a mandatory safe-language rule. Invalid scopes, repeated keys/selectors, invalid values, mismatches with the ordinary signature/effect row, or insufficient audited safety guarantees are interface errors.

A protocol reference names a stable canonical contract identity. The same semantic block MUST include exactly one `ffi-protocol path = "description";` for every referenced protocol, and descriptions must be self-contained with respect to their audited protocol behavior. Descriptions normalize line endings to LF; their remaining text is contract content, not subject to a prose-equivalence solver. The normalized description is part of the audited semantic contract and machine metadata, and MUST render all remaining client-relevant facts faithfully in human-readable terms; an opaque identifier/hash alone is insufficient. For a stack-preserving protocol this includes all §56.1 obligations, and for a retained registration it includes the terminal drain/discharge outcomes of §56.2.1. Tools may display the escaped string as prose, but must preserve its content in canonical serialization and semantic diffs. A changed guarantee, obligation, or protocol description invalidates semantic dependents independently of ABI changes.

Canonical rendering emits properties in the table's key order (a shared key appears once at its applicable subject), then subject blocks in the order `parameter`, `result`, `member`, `component`, `pointer`, `output`, `callback`, `marshalling`. Parameter/component selectors sort by numeric index, member selectors by canonical identity, recursively. Protocol descriptions follow the contract, sorted by canonical identity. Capture bounds use §77's ordering. The same normalized metadata MUST produce the same keys, selector identities, protocol identities/descriptions, and order independently of source labels or input metadata order.

For example, this is generated interface output, not source:

```text
module native;
pub fn call(callback: fn() -> Unit) -> Unit;
semantic {
    ffi-contract {
        invocation = synchronous;
        blocking = none;
        finite-return = guaranteed;
        native-cancellation = unsupported;
        foreign-unwind = no_unwind;
        parameter(0) {
            callback {
                lifetime = call_scoped;
                cardinality = exactly_once;
                reentrancy = forbidden;
                thread-affinity = same_domain_thread;
                delivery-domain = current_domain;
                barrier = ordinary;
                suspension = forbidden;
                algebraic-crossing = forbidden;
                cancellation = deferred;
                defect = protocol(native::CallRendezvous);
                pending-defect-entry = suppressed;
                deregistration = not_applicable;
                drain = not_applicable;
                undelivered = not_applicable;
                shutdown = not_applicable;
            }
        }
    }
    ffi-protocol native::CallRendezvous = "The shim returns a private native failure status on a defect or suppressed entry. Native code then returns to the waiting Eldude boundary. No pending invocation resumes normal Eldude work.";
}
```

The `exactly_once` clause describes normally completed lifecycles; defects still follow §§20 and 56. The protocol description supplies the audited control path behind the `defect` clause, not a recoverable application result.

## 73. Generic compilation

### 73.1 No mandatory whole-program monomorphization

Ordinary generic Eldude code MUST admit separate compilation without requiring the complete set of future instantiations.

The backend may implement generic code using:

- uniform/shared representations;
- dictionaries/witness tables;
- shared generic machine code;
- per-instantiation specialization;
- monomorphization where profitable;
- combinations of these.

No one strategy is mandated by the language.

### 73.2 Optional specialization

Cross-module specialization is an optimization. It may depend on implementation bodies or optimization IR but does not change semantic validity.

Removing a specialization opportunity must not change program meaning.

### 73.3 Static naturals and layout

`Array<T,N>` and other statically indexed types may require instantiation-specific layout/code generation. This does not permit ordinary semantic checking to become whole-program dependent.

## 74. ABI and representation

### 74.1 Value-semantics freedom

Unless a public ABI/FFI contract explicitly fixes representation, the implementation may choose:

- stack or heap placement;
- boxed or unboxed representation;
- pointer compression;
- copy-on-write;
- reference counting;
- tracing collection;
- destructive reuse of dead storage;
- scalar replacement;
- specialization.

Safe source cannot observe physical relocation of ordinary values.

### 74.2 Public ABI

When a module exposes a stable binary ABI, the canonical ABI interface separately records the layout/calling-convention facts needed by consumers.

Semantic opacity and ABI opacity are related but not identical: a type may hide source-level fields while still committing to a binary layout for a foreign boundary, or expose source fields without promising a stable cross-version ABI.

### 74.3 FFI trust metadata

Generated/imported native bindings SHOULD separate:

- mechanically derived ABI facts; and
- audited semantic annotations such as ownership, retention, suspension, callback lifetime/cardinality/reentrancy, defect-rendezvous, and termination contracts.

Changing an audited semantic contract invalidates semantic dependents even when the C ABI did not change.

### 74.4 Canonical native-binding metadata

The standard toolchain MUST define a deterministic machine-readable representation for imported/generated native contracts. It must keep mechanically derived ABI facts distinct from audited semantic facts and be capable of representing at least the categories required by §§52–57: ownership transfer; pointer retention, mutability, aliasing, and stable-address requirements; output initialization; callback lifetime, cardinality, per-registration reentrancy, thread affinity, and delivery domain; ordinary versus audited-stack-preserving synchronous-callback mode; foreign-control-barrier behavior; callback suspension permission; cancellation rendezvous; blocking/offload classification; finite-return/`diverge` contract; defect rendezvous; foreign exception/unwind policy; deregistration/in-flight-drain behavior; and scoped temporary-marshalling lifetime/provenance.

An ordinary synchronous callback declaration canonically means the conservative §56.1 foreign-control barrier unless its audited host/native contract explicitly selects the stack-preserving exceptional protocol. No metadata default may imply support for cross-foreign-frame algebraic continuation transfer.

Generated Eldude interfaces MUST render every client-relevant audited fact using ordinary types, effects, captures, `Cleanup`, unsafe preconditions, and the complete generated FFI clauses/protocol descriptions of §72.9. In particular, the metadata includes pending-defect entry suppression and complete-lifecycle undelivered-callback obligations (§§56.1–56.2.1). Tooling SHOULD support semantic diffing so a change to an audited contract is reviewable independently of an unchanged C ABI. This is tooling/interface structure, not a new source-language capability system.

## 75. Incremental checking

### 75.1 Semantic invalidation

If a module's canonical semantic interface hash is unchanged, downstream modules SHOULD reuse previous semantic-check results.

### 75.2 Private edit

A private body edit should invalidate only:

- the edited module's local checking/code generation;
- optimization artifacts that actually depended on the changed body;
- downstream code generation only when required by the chosen optimization strategy.

It should not force downstream re-typechecking solely because an implementation body changed.

### 75.3 Public edit

A public semantic-interface change invalidates downstream modules whose direct/transitive semantic dependency observes the changed fact.

Tooling SHOULD report the semantic reason for invalidation where practical.

## 76. Diagnostics

### 76.1 Source-level terminology

Diagnostics MUST use source-level concepts rather than exposing internal solver structures as the primary explanation.

Important categories include:

```text
effect mismatch
unproved termination / inferred diverge
unexpected suspension contract
non-exhaustive match
trait coherence violation
dynamic trait interface has a method without a receiver
dynamic trait method introduces method-local generics
dynamic trait method exposes concrete Self outside the receiver
dynamic trait method uses a GAT projection
dynamic trait associated type is not fixed by the package
dynamic trait method constraint is not derivable from the package interface
dynamic trait method contract depends on hidden concrete-type information
region escape
capture/provenance escape
Dup requirement not satisfied
Discard requirement not satisfied
linear obligation not consumed
callable consumed more than once
access conflict
illegal mut on aliasable/shared state
lexical handler incompleteness
invalid resumption multiplicity
illegal affine continuation abandonment
opaque effect row may abandon live obligation
effect row does not satisfy NonAbandoning
result capture/provenance relationship violation
retained value outlives storage horizon
temporary foreign view escapes marshalling scope
suspension crosses synchronous foreign-control barrier
algebraic handler lies beyond synchronous foreign-control barrier
callback registration may outlive retained provenance or in-flight delivery
non-Dup handler cannot be inherited by child
ambiguous effect instance
task handle escaping taskgroup
spawn result not Discard
child capture cannot cross task boundary
unsafe operation outside unsafe block
public declaration missing semantic contract
compile-time natural mismatch
invalid Cleanup implementation
FFI contract inconsistency
```

### 76.2 Retention paths

For capture/lifetime errors, diagnostics SHOULD display the shortest useful retention path.

Example:

```text
cannot return value:
  result
  -> closure `next`
  -> cell
  -> Ref<State,@scratch>
  -> region @scratch ends here
```

### 76.3 Control-segment diagnostics

For illegal affine continuation abandonment, diagnostics SHOULD identify the blocking obligation in the captured segment, for example:

```text
cannot abandon continuation:
  captured frame retains `file: File`
  File is not Discard and has no structural discharge owner
```

or:

```text
cannot abandon continuation:
  captured taskgroup owns unfinished child `worker`
```

### 76.4 Derived effect-control diagnostics

When `NonAbandoning` is required but cannot be proved, diagnostics SHOULD identify the concrete row entry responsible whenever possible rather than only reporting a failed intrinsic constraint. For example:

```text
effect row `e` is not NonAbandoning:
  `suspend` permits cooperative cancellation of the continuation
```

or:

```text
effect family `Choice` is not NonAbandoning:
  operation `choose` is declared `affine`
```

When this blocks a live ownership obligation, the diagnostic SHOULD also show the shortest relevant continuation/retention path and may suggest adding `where e: NonAbandoning` when the generic API genuinely intends that contract.

### 76.5 Redundant syntax diagnostics

The compiler MAY warn about semantically redundant annotations such as `view` on an unrestricted immutable value or repeated usage strengthening already implied by fields.

Warnings must not change parsing/type semantics.

## 77. Formatting and source stability

A deterministic formatter is part of the standard toolchain.

Formatting is not parsing semantics. The parser must accept valid brace/semicolon syntax independent of indentation.

Compiler-generated public signatures MUST use the same canonical surface conventions as the formatter, including bare effect-row variables inside `{...}` and ordinary `where e: NonAbandoning` spelling for the intrinsic effect-row constraint. They MUST also include the human-readable generated semantic clauses required by §72.7 whenever a client-validity fact such as result provenance or mutable-owner status is not otherwise visible in the ordinary signature.

Generated canonical interfaces MUST render semantically unordered collections in one deterministic textual order:

- algebraic effect families and nominal error alternatives sort by canonical fully qualified identity;
- `state<@r>` entries sort by canonical region-binder identity/order rather than incidental source spelling;
- open row variables sort by binder order;
- intrinsic effect entries follow named/state entries in the fixed order `suspend`, then `diverge`;
- generated capture/provenance unions sort `captures(x)` entries by canonical source slot (callable environment, then all arguments by parameter position, using accessed-value summaries for access-mode slots; source names are display labels only), then explicit provenance atoms by category and canonical binder/identity order, then capture-row variables by binder order;
- unordered constraint collections sort first by constrained binder order and then by canonical predicate identity;
- generated finite-positive parameter index sets sort in ascending parameter-position order.

User-authored source need not be reordered solely to match this interface order; the requirement is for generated canonical renderings, stable hashing inputs, and deterministic generated documentation.

## 78. Testing

The core language has no dedicated `test` declaration or `expect` statement.

Test discovery, fixtures, property testing, snapshots, and runners are tooling/library conventions.

The toolchain SHOULD support:

- tests adjacent to source;
- isolated test execution;
- running independently checkable tests even when unrelated modules contain errors, where dependency structure permits;
- clear distinction between successful selected tests and unrelated workspace compilation failures.

A workspace with unresolved required compilation errors MUST NOT be presented as globally successful.

# Appendix A — Deliberately Absent or Deferred Features

This appendix is normative with respect to the current design scope. It is not a claim that these features can never be added.

## A.1 General reference/lifetime machinery

The current design excludes:

- general safe `&T` / `&mut T` references;
- source lifetime parameters/outlives constraints;
- general borrow expressions;
- first-class borrowed slices into mutable owners;
- Rust-style borrow inference.

Temporary access uses `view`/`mut`; retained mutable identity uses region-indexed nominal abstractions; interior inspection uses scoped projection.

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

## A.4 Type-system surface deferred

The current design excludes or defers:

- structural records;
- structural variants;
- `some Trait`;
- general explicit existential syntax;
- surface type-level lambdas;
- refinement-type syntax;
- units-of-measure syntax;
- session/protocol syntax;
- unrestricted type-level general recursion;
- arbitrary theorem proving during ordinary checking.

GADTs, nominal opacity, associated types, GATs, higher-rank/higher-kinded polymorphism, and compile-time naturals provide the current abstraction surface.

## A.5 Syntax conveniences deferred

The current design excludes:

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
- exact names/breadth of ownership-preserving projection and traversal combinators satisfying §§15 and 35;
- exact names/breadth of structured-concurrency combinators satisfying §46.6;
- explicit parallel-computation library, if later justified;
- specialized native arenas/supervision libraries.

## A.8 Deferred or removed algebraic-control variants

The 0.0.2 core has no separate `abort` resumption mode. Abortive operations use `affine ... -> Never`, so continuation abandonment follows the ordinary affine rule.

Many-shot algebraic resumption is deferred. Reintroducing it would require a demonstrated need for continuation duplication plus a separately reviewed composition story for usage, mutable state, handlers, concurrency, and separate compilation. It is not accepted merely as the completion of a resumption-mode feature matrix.


# Appendix B — Canonical Examples

## B.1 Pure non-diverging function

```eldude
fn add(x: Int, y: Int) -> Int {
    x + y
}
```

## B.2 Effect-polymorphic higher-order function

```eldude
fn apply<A, B, !e, ..C>(
    f: fn(A) ->{e} B captures {..C},
    value: A,
) ->{e} B {
    f(value)
}
```

The callback is invoked exactly once, so no `Dup`/`Discard` constraint on `..C` is needed solely for invocation multiplicity.

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
    f: fn(T) ->{e} Unit captures {..C},
) ->{e} Unit
where e: NonAbandoning,
      ..C: Dup + Discard
{
    ...
}
```

An unconstrained open row remains conservatively potentially abandoning.

## B.4 Linear closure

```eldude
linear struct File;

let closeLater = fn() {
    close(file);
};

closeLater();
// second call is illegal: callable instance was consumed
```

## B.5 Region-local mutation

```eldude
fn encode(values: List<Byte>) -> List<Byte> {
    region scratch {
        let out: DynArray<Byte, @scratch> = DynArray::new();

        for value in values {
            mut out.push(value);
        }

        out.freeze()
    }
}
```

`state<@scratch>` is eliminated because no result/capture retains `@scratch`.

## B.6 Aliasable state

```eldude
region r {
    let cell: Ref<Int, @r> = Ref::new(0);

    cell.set(1);
    let x = cell.get();
    x
}
```

`Int: Dup + Discard`, so it is permitted as a `Ref` payload and may be read by value.

## B.7 Non-`Dup` collection inspection

```eldude
view values.with(index, fn(view item) {
    inspect(view item)
});
```

No reference value escapes the callback.

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
    }
}
```

The explicit `finish` reports meaningful failure. Any still-live cleanup-owned resource is discharged by `using` during scope exit.

## B.10 Algebraic effect and lexical handler

```eldude
effect Console {
    tail print(text: Text) -> Unit;
    once readLine() -> Text;
}

fn greet() ->{Console} Unit {
    !Console::print("Name: ");
    let name = !Console::readLine();
    !Console::print(name);
}

fn runGreeting() ->{io} Unit {
    handle {
        greet()
    } with handler Console {
        print(text) => {
            terminalWrite(text);
            resume(());
        }

        readLine() => {
            resume(terminalRead());
        }
    }
}
```

The handler is lexical and not a first-class `Handler` value. A reusable interpreter can be expressed by an ordinary wrapper function that installs the same lexical handler around a supplied computation.

## B.11 Forwarding

```eldude
fn runPrintOnly(body: fn() ->{Console} Unit) ->{log, Console} Unit {
    handle {
        body()
    } with handler Console {
        print(text) => {
            writeLog(text);
            resume(());
        }

        forward readLine;
    }
}
```

The wrapper's residual row contains both the logging effect and `Console` because `readLine` may be forwarded.

## B.12 Affine delimiter abandonment safety

Potentially safe because structural cleanup owns the resource:

```eldude
using (file = open(path)?) {
    handle {
        let choice = !Choice::choose();
        inspect(view file, choice)
    } with handler Choice {
        choose() => {
            // zero or one resume according to the handler logic
            ...
        }
    }
}
```

A zero-resumption `affine` path may abandon the captured continuation only when the structural-exit law can discharge every retained obligation.

Invalid with a naked linear obligation inside the abandoned segment:

```eldude
handle {
    let file = openLinear(path)?;
    let choice = !Choice::choose();
    consumeWithChoice(file, choice)
} with handler Choice {
    choose() => {
        // choosing zero resumptions would abandon `file`
        ...
    }
}
```

A zero-resumption affine path would abandon `file` without a legal discharge owner, so the composition is rejected.

## B.13 Typed failure with explicit nominal mapping

```eldude
enum LoadError {
    IO(IOError),
    Parse(ParseError),
}

fn load(path: Path) -> Result<LoadError, Config>
{
    let bytes =
        readFile(path).mapError(LoadError::IO)?;
    parse(bytes).mapError(LoadError::Parse)?
}
```

`?` propagates only the chosen nominal error type. Different nominal errors require explicit mapping.

## B.14 Assertions

```eldude
fn internalInvariant(x: State) -> Unit {
    assert x.valid();
}
```

Assertion failure is a defect; it is not represented in the function's effect row or as `Result`.

## B.15 Structured concurrency

```eldude
enum FetchBothError {
    User(UserError),
    Orders(OrderError),
}

fn fetchBoth(id: UserId)
    ->{net, suspend, diverge}
      Result<FetchBothError, Pair>
{
    taskgroup {
        let userTask = spawn fetchUser(id);
        let orderTask = spawn fetchOrders(id);

        Pair {
            user: (await userTask).mapError(FetchBothError::User)?,
            orders: (await orderTask).mapError(FetchBothError::Orders)?,
        }
    }
}
```

Both spawned result types must be `Discard`. The parent explicitly maps distinct child error types into one nominal error type before `?` propagation.

## B.16 Discarded task handle

```eldude
taskgroup {
    spawn refreshCache();
    serveRequest()
}
```

Discarding the handle does not cancel the child. The taskgroup still waits for it at normal exit or cancels/drains it on abnormal exit.

## B.17 Explicit cancellation

```eldude
taskgroup {
    let worker = spawn backgroundWork();

    if noLongerNeeded() {
        worker.cancel();
    }
}
```

`cancel()` is request-only and consumes the handle. The taskgroup boundary is the final rendezvous.

## B.18 Handler scope and children

Whole subtree:

```eldude
handle {
    taskgroup {
        spawn workA();
        spawn workB();
    }
} with handler E {
    ...
}
```

One child only:

```eldude
taskgroup {
    spawn handle {
        workA()
    } with handler E {
        ...
    };

    spawn workB();
}
```

A transient parent handler entered after group creation is not automatically inherited by children. Child inheritance of a baseline handler frame still obeys the ordinary `Dup` requirement on values retained by that frame.

## B.19 Opaque foreign callback identity

Conceptually:

```eldude
using (registration = ffi::registerCallback(state, callback)?) {
    run();
}
```

A bundled runtime wrapper may internally use an opaque rooting handle such as `ffi::Handle<State>`. `State` itself remains movable; the exact wrapper type is not a core-language requirement.

## B.20 Stable native storage

Conceptually:

```eldude
using (native = ffi::Box::new(CState { ... })?) {
    unsafe {
        c_register(view native.ptr());
    }

    run();
}
```

Stable address belongs to the explicit native allocation wrapper, not to ordinary `CState` values; `ffi::Box` is a bundled runtime-library example rather than a core-language primitive.


## B.21 Synchronous foreign callback with callback-local algebraic control

Conceptually:

```eldude
callNativeWithCallback(fn() {
    handle {
        !Choice::choose()
    } with handler Choice {
        choose() => {
            resume(true);
        }
    }
});
```

This is permitted when the native callback contract is otherwise safe: the `Choice` operation is interpreted entirely on the callback side of the foreign-control barrier and the residual callback contract does not admit `suspend`.

## B.22 Rejected cross-foreign-frame algebraic control

```eldude
handle {
    callNativeWithCallback(fn() {
        !Choice::choose()
    })
} with handler Choice {
    choose() => {
        resume(true);
    }
}
```

This composition is rejected for an ordinary synchronous callback even if `choose` is `tail` or `once`. The matching handler lies outside the waiting foreign frame, and `NonAbandoning` does not authorize continuation capture/resumption through that frame.

## B.23 Rejected suspension in an ordinary synchronous callback

```eldude
callNativeWithCallback(fn() {
    task::yield()
});
```

The callback admits `suspend` and is rejected by the ordinary foreign-control barrier. A separately audited stack-preserving callback protocol may permit suspension, but it must satisfy §56.1 and does not thereby permit algebraic control to cross the barrier.

## B.24 Retained foreign-thread callback registration

Conceptually:

```eldude
using (registration = ffi::registerPostedCallback(state, callback)?) {
    run();
}
```

This `using` form is valid only when callback skipping is `Discard`-permitted or cleanup guarantees invocation/structural discharge under §56.2.1. The registration is a structured lifetime owner. Its cleanup/deregistration protocol prevents new delivery and drains or terminally accounts for accepted/in-flight posted callbacks before releasing retained Eldude captures or rooting handles.

# Appendix C — Architectural Precedents

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

# Appendix D — Evaluation Criteria for an Implementation

Eldude's design claims are semantic goals, not implementation-performance results.

A compiler/runtime SHOULD publish measurements for:

- clean build time;
- private-body incremental edit latency;
- public-interface edit latency;
- time to first diagnostic;
- peak compiler memory;
- generic code size;
- handler cost by resumption mode;
- non-divergence-analysis cost;
- capture/usage-checking cost;
- `List` copy-on-write/reuse behavior;
- linear collection traversal cost;
- region mutation overhead;
- task spawn/await/cancellation overhead;
- taskgroup shutdown latency;
- FFI transition and callback-posting cost;
- interface hash stability and incremental cache hit rate.

Claims relative to Haskell, Koka, Rust, OCaml, Roc, or other languages require measured evidence on stated workloads and toolchain versions.

# Appendix E — Consolidated Architectural Invariants

This appendix restates the most important cross-feature invariants in compact form. It is normative where it repeats earlier requirements.

```text
1. Ordinary values are movable and have value semantics.
2. Dup and Discard are the only fundamental usage permissions.
3. Discard never runs hidden user effects.
4. Captures track retention; callable contracts also preserve result-capture relationships through abstraction and erasure.
5. view/mut are call-scoped permissions, never reference values; ordinary arguments and method receivers expose those grants explicitly at the call site. Root mut access charges region state; forwarding/projection carries supplied state authority, and explicitly declared effects remain accounted.
6. Root mut grant formation requires a compiler-recognized non-duplicable mutable owner; non-Dup alone does not create mutable identity. Supplied grants may target arbitrary projected subvalues.
7. Ref<T,@r> requires T: Discard; reading by value additionally requires T: Dup; stored payload provenance must remain valid for at least @r.
8. state<@r> is intrinsic and eliminated only by a non-escaping region boundary.
9. Cleanup is explicit through using and canonical Cleanup; no implicit destructor-on-discard exists, and no residual abandon-capable algebraic control may escape Cleanup.
10. Lexical `handle` expressions have complete residual effect contracts; active handler frames have one usage state, and each returning `resume` transfers non-Dup frame captures into the resumed computation without restoring them to post-resume clause code.
11. Effect rows have a context-relative derived continuation-control envelope; unmasked suspend and affine families may abandon continuations and are checked at opaque call boundaries.
12. Result::Err is data; assertions are nonrecoverable defects and are not statically checked as recoverable obligation-discharge exits.
13. suspend marks possible strand yielding; every actual unmasked suspension point is a potential cancellation-delivery point and must be statically safe as a continuing structural exit.
14. taskgroup/spawn/await are cooperative concurrency, not shared-memory parallelism.
15. spawn results must be Discard.
16. Task<T> handles are unique optional observation/cancel rights; taskgroups own child lifetime.
17. Discarding Task<T> does not cancel it.
18. Task handles cannot escape their lexical taskgroup; captures enforce this without lifetime syntax.
19. Child effects belong to the lexical taskgroup, not to Task<T>.
20. Children may inherit only Dup handler frames from the environment enclosing the taskgroup; arbitrary transient or non-Dup parent handler frames are not implicitly shared.
21. No general Send/Sync/Transfer or pinning axis exists.
22. Stable foreign identity, stable native storage, and temporary FFI pointers are distinct abstractions. Safe temporary marshalling introduces fresh scoped foreign provenance that cannot escape its callback horizon.
23. Unsafe grants designated low-level operations but never disables ordinary static checking.
24. The host is the single outer runtime boundary; libraries expose ordinary effect contracts. A conforming runtime does not indefinitely stutter while runnable Eldude work exists; this minimal progress rule is weaker than general fairness.
25. Canonical interfaces contain every client-relevant semantic fact, including result-capture and mutable-owner facts, and are sufficient for separate checking.
26. Many-shot algebraic resumption is deferred from the 0.0.2 core rather than forcing continuation-duplication machinery into every composition rule.
27. `any Trait<...>` formation is governed by one closed `DynCompatible` judgment decidable from canonical interface data; dynamic erasure never relies on implementation-defined object-safety intuition.
28. `NonAbandoning` is the sole source-level constraint on the derived continuation-abandonment property of effect rows; it is intrinsic and not user-implementable.
29. Standard projection, traversal, and structured-concurrency combinators preserve the same ownership, provenance, effect, cancellation, and taskgroup laws as their core primitives; library ergonomics do not create hidden escape mechanisms.
30. An ordinary same-domain synchronous foreign callback executes beneath an internal foreign-control barrier: it cannot admit `suspend`, algebraic handler lookup cannot cross the waiting foreign frame, pending cooperative cancellation is deferred until a later ordinary Eldude suspension point, and defects use audited rendezvous rather than foreign-frame unwinding. An audited stack-preserving protocol may permit suspension but does not by itself permit cross-foreign-frame algebraic continuations.
31. Retained foreign-thread callbacks execute by posting into an Eldude domain and are owned by an explicit registration lifetime that deregisters and drains accepted/in-flight delivery before releasing retained Eldude state.
32. Data-field projection requires Dup of the selected field and preserves a bound aggregate; owned patterns consume the whole matched value, and ignored owned values require Discard. A computed owned projection receiver additionally requires Discard; optional field projection follows the same rules.
```

# Appendix F — Complete Normative Source and Interface Grammar

The normative artifact is [eldude.ebnf](eldude.ebnf). This appendix, the standalone [formal grammar](ELDUDE-FORMAL-GRAMMAR.md), and [JSON export](eldude-grammar.json) are generated by `python3 tools/check_grammar.py --write`; `python3 tools/check_grammar.py` rejects undefined symbols, duplicate productions, malformed EBNF, reserved-word drift, or any stale presentation. Syntax conformance cases run with `python3 -m unittest discover -s tools -p 'test_grammar*.py'`. The checker is a syntax recognizer, not an Eldude type checker or compiler.

`source_file` is the ordinary source entry point and requires exactly one initial module declaration. `interface_file` separately permits generated semantic clauses after declarations. Type/access/visibility restrictions remain semantic checks; grammar acceptance alone does not imply program validity. `?`, `*`, and `+` outside quoted terminals are EBNF repetition operators. `%token` and `%skip` declare regular-expression lexical rules; `%keywords` excludes those words from `IDENT`. All punctuation uses longest matching. Source conventions and the nearest-function capture-clause association are defined in §2.8.

<!-- BEGIN GENERATED ELDUDE GRAMMAR -->
```ebnf
# Normative Eldude 0.0.2 EBNF. Generated presentations: Appendix F and the Formal Grammar.
# EBNF: ::= definition; | choice; () grouping; ? optional; * repetition; + one or more.
# JSON strings quote terminals and lexical regular expressions; # begins a whole-line comment.
%skip SPACE = "[ \\t\\r\\n]+";
%skip LINE_COMMENT = "//[^\\r\\n]*";
%skip BLOCK_COMMENT = "/\\*(?:[^*]|\\*(?!/))*\\*/";
%token FLOAT_LITERAL = "(?:[0-9](?:_?[0-9])*\\.[0-9](?:_?[0-9])*(?:[eE][+-]?[0-9](?:_?[0-9])*)?|[0-9](?:_?[0-9])*[eE][+-]?[0-9](?:_?[0-9])*)(?:f32|f64)?|[0-9](?:_?[0-9])*(?:f32|f64)";
%token INT_LITERAL = "(?:0b[01](?:_?[01])*|0o[0-7](?:_?[0-7])*|0x[0-9a-fA-F](?:_?[0-9a-fA-F])*|[0-9](?:_?[0-9])*)(?:i8|i16|i32|i64|i128|u8|u16|u32|u64|u128|int|uint|nat)?";
%token STRING_LITERAL = "\"(?:[^\"\\\\\\x00-\\x1f]|\\\\(?:[\"\\'\\\\nrt0]|u\\{[0-9a-fA-F]{1,6}\\}))*\"";
%token CHAR_LITERAL = "'(?:[^'\\\\\\x00-\\x1f]|\\\\(?:[\"\\'\\\\nrt0]|u\\{[0-9a-fA-F]{1,6}\\}))'";
%token IDENT = "[A-Za-z_][A-Za-z_0-9]*";
%keywords "affine any as assert await break captures case const continue decreases effect else enum extern false fn for forall forward handle handler if impl import in intrinsic let linear match module mut once pub region resume return self spawn struct suspend taskgroup trait true try type unsafe using view where while diverge";

# Files and declarations
source_file ::= "module" path ";" module_item*;
module_item ::= import_decl | declaration;
import_decl ::= "pub"? "import" path "::" "{" import_names "}" ";";
import_names ::= import_name ("," import_name)* ","?;
import_name ::= IDENT ("as" IDENT)?;
declaration ::= "pub"? (function_decl | let_decl | struct_decl | enum_decl | trait_decl | effect_decl | alias_decl) | impl_decl | extern_block;
function_decl ::= "unsafe"? "fn" IDENT generic_params? parameters result_contract where_clause? decreases_clause? (block | ";");
let_decl ::= "let" pattern (":" type)? "=" expr ";";
struct_decl ::= usage_modifier? "struct" IDENT generic_params? where_clause? ("{" fields? "}" | ";");
usage_modifier ::= "linear" | "affine";
fields ::= field_decl ("," field_decl)* ","?;
field_decl ::= "pub"? IDENT ":" type;
enum_decl ::= usage_modifier? "enum" IDENT generic_params? (where_clause? "{" variants? "}" | "where" "{" gadt_constructors? "}");
variants ::= variant ("," variant)* ","?;
variant ::= "pub"? IDENT ("(" type_list? ")" | "{" fields? "}")?;
gadt_constructors ::= gadt_constructor ("," gadt_constructor)* ","?;
gadt_constructor ::= "pub"? IDENT ":" type;
trait_decl ::= "intrinsic"? "trait" IDENT generic_params? where_clause? "{" trait_member* "}";
trait_member ::= method_decl | associated_decl;
method_decl ::= "unsafe"? "fn" IDENT generic_params? parameters result_contract where_clause? decreases_clause? (block | ";");
associated_decl ::= "type" IDENT generic_params? where_clause? ";";
associated_equation ::= "type" IDENT generic_params? where_clause? "=" type ";";
impl_decl ::= "impl" generic_params? type ("for" type)? where_clause? "{" impl_member* "}";
impl_member ::= "pub"? method_decl | associated_equation;
effect_decl ::= "effect" IDENT generic_params? "{" effect_operation* "}";
effect_operation ::= ("tail" | "once" | "affine") IDENT parameters "->" type ";";
alias_decl ::= "type" IDENT generic_params? "=" type ";";
extern_block ::= "extern" STRING_LITERAL "{" ("pub"? function_decl)* "}";
parameters ::= "(" (parameter ("," parameter)* ","?)? ")";
parameter ::= access_mode? binding_name ":" type | access_mode? "self";
access_mode ::= "view" | "mut";
binding_name ::= IDENT | "self";
result_contract ::= "->" effect_row? type capture_clause?;
where_clause ::= "where" constraint ("," constraint)* ","?;
constraint ::= constraint_subject ":" constraint_bounds | type "=" type;
constraint_subject ::= type | ".." IDENT;
constraint_bounds ::= type ("+" type)*;
decreases_clause ::= "decreases" condition_expr;

# Types, binders, and category slots
path ::= path_part ("::" path_part)*;
path_part ::= IDENT | "self";
generic_params ::= "<" generic_param ("," generic_param)* ","? ">";
generic_param ::= IDENT ("<" placeholders ">")? | "@" IDENT | "!" IDENT | ".." IDENT | "#" IDENT;
placeholders ::= "_" ("," "_")*;
type ::= forall_type | function_type | raw_pointer_type | any_type | tuple_type | applied_path | qualified_projection;
forall_type ::= "forall" generic_params "." type;
function_type ::= "fn" "(" (mode_type ("," mode_type)* ","?)? ")" result_contract;
mode_type ::= access_mode? type;
raw_pointer_type ::= "*" ("const" | "mut") type;
any_type ::= "any" applied_path ("+" applied_path)*;
tuple_type ::= "(" ")" | "(" type "," (type ("," type)* ","?)? ")" | "(" type ")";
applied_path ::= path type_args? ("::" IDENT type_args?)*;
qualified_projection ::= "<" type "as" applied_path ">" "::" IDENT type_args?;
type_args ::= "<" type_arg ("," type_arg)* ","? ">";
type_arg ::= type | region_ref | effect_row | capture_set | ".." IDENT | nat_expr | IDENT "=" type;
type_list ::= type ("," type)* ","?;
region_ref ::= "@" IDENT;
effect_row ::= "{" (effect_entry ("," effect_entry)* ","?)? "}";
effect_entry ::= path | "state" "<" region_ref ">" | "suspend" | "diverge";
capture_clause ::= "captures" capture_set;
capture_set ::= "{" (capture_entry ("," capture_entry)* ","?)? "}";
capture_entry ::= region_ref | ".." IDENT | path;
nat_expr ::= nat_product ("+" nat_product)*;
nat_product ::= nat_atom ("*" nat_atom)*;
nat_atom ::= INT_LITERAL | IDENT | "(" nat_expr ")";

# Expressions and fixed precedence
# Undelimited lambda bodies/return operands take the longest expression under §2.8.
expr ::= coalesce_expr;
coalesce_expr ::= equality_expr ("??" coalesce_expr)?;
equality_expr ::= relational_expr (equality_op relational_expr)?;
equality_op ::= "==" | "!=";
relational_expr ::= sum_expr (relational_op sum_expr)?;
relational_op ::= "<" | "<=" | ">" | ">=";
sum_expr ::= product_expr (("+" | "-") product_expr)*;
product_expr ::= unary_expr (("*" | "/" | "%") unary_expr)*;
unary_expr ::= ("+" | "-" | "await" | "spawn") unary_expr | postfix_expr;
postfix_expr ::= primary postfix*;
postfix ::= arguments | "." IDENT | ".?" IDENT | turbofish | "?" | "[" expr "]";
turbofish ::= "::" type_args;
arguments ::= "(" (argument ("," argument)* ","?)? ")";
argument ::= access_mode binding_name | expr;
primary ::= literal | path | struct_literal | tuple_expr | list_literal | lambda | block | if_expr | match_expr | while_expr | for_expr | scoped_expr | using_expr | handle_expr | access_method | operation_call | resume_expr | exit_expr;
literal ::= INT_LITERAL | FLOAT_LITERAL | STRING_LITERAL | CHAR_LITERAL | "true" | "false";
struct_literal ::= path "{" value_fields? "}";
value_fields ::= value_field ("," value_field)* ","?;
value_field ::= IDENT (":" expr)?;
tuple_expr ::= "(" ")" | "(" expr "," (expr ("," expr)* ","?)? ")" | "(" expr ")";
list_literal ::= "[" (expr ("," expr)* ","?)? "]";
lambda ::= "fn" "(" (lambda_param ("," lambda_param)* ","?)? ")" ("=>" expr | result_contract? block);
lambda_param ::= access_mode? binding_name (":" type)?;
block ::= "{" statement* expr? "}";
statement ::= let_decl | "assert" expr ";" | expr ";" | block_statement;
block_statement ::= while_expr | for_expr;
if_expr ::= "if" condition_expr block ("else" (block | if_expr))?;
match_expr ::= "match" condition_expr "{" match_arm* "}";
match_arm ::= "case" pattern ("if" condition_expr)? "=>" expr ";";
while_expr ::= "while" condition_expr decreases_clause? block;
for_expr ::= "for" pattern "in" condition_expr decreases_clause? block;
scoped_expr ::= "region" IDENT block | ("try" | "taskgroup" | "unsafe") block;
using_expr ::= "using" "(" acquisition ("," acquisition)* ","? ")" block;
acquisition ::= binding_name "=" expr;
access_method ::= access_mode binding_name "." IDENT turbofish? arguments;
operation_call ::= "!" path arguments;
resume_expr ::= "resume" arguments;
exit_expr ::= "return" expr? | "break" | "continue";
handle_expr ::= "handle" block "with" (IDENT "=")? "handler" applied_path "{" handler_clause* "}";
handler_clause ::= IDENT "(" patterns? ")" "=>" expr ";"? | "return" pattern "=>" expr ";"? | "forward" (IDENT | "..") ";";

# Control conditions exclude an unparenthesized nominal literal at the outer level.
condition_expr ::= condition_equality ("??" condition_expr)?;
condition_equality ::= condition_relation (equality_op condition_relation)?;
condition_relation ::= condition_sum (relational_op condition_sum)?;
condition_sum ::= condition_product (("+" | "-") condition_product)*;
condition_product ::= condition_unary (("*" | "/" | "%") condition_unary)*;
condition_unary ::= ("+" | "-" | "await" | "spawn") condition_unary | condition_primary postfix*;
condition_primary ::= literal | path | tuple_expr | list_literal | lambda | block | if_expr | match_expr | while_expr | for_expr | scoped_expr | using_expr | handle_expr | access_method | operation_call | resume_expr | exit_expr;

# Owned and inspection patterns share syntax; typing determines ownership.
pattern ::= pattern_atom ("|" pattern_atom)*;
pattern_atom ::= "_" | signed_literal | path ("(" patterns? ")" | "{" pattern_fields? "}")? | tuple_pattern;
signed_literal ::= ("+" | "-")? (INT_LITERAL | FLOAT_LITERAL) | STRING_LITERAL | CHAR_LITERAL | "true" | "false";
tuple_pattern ::= "(" ")" | "(" pattern "," (pattern ("," pattern)* ","?)? ")" | "(" pattern ")";
patterns ::= pattern ("," pattern)* ","?;
pattern_fields ::= pattern_field ("," pattern_field)* ","?;
pattern_field ::= IDENT (":" pattern)?;

# Distinct generated canonical interfaces. These productions are unreachable from source_file.
interface_file ::= "module" path ";" interface_item*;
interface_item ::= import_decl | declaration semantic_block?;
semantic_block ::= "semantic" "{" semantic_clause* "}";
semantic_clause ::= "result-captures" "<=" capture_bound ";" | "mutable-owner-region" "=" region_ref ";" | "finite-positive-parameters" "=" "{" index_list? "}" ";" | ffi_contract | ffi_protocol | semantic_selector "{" semantic_clause* "}";
index_list ::= INT_LITERAL ("," INT_LITERAL)*;
capture_bound ::= "{" (generated_capture ("," generated_capture)* ","?)? "}";
generated_capture ::= "captures" "(" (binding_name | "parameter" "(" INT_LITERAL ")" | "..") ")" | capture_entry;
semantic_selector ::= "parameter" "(" INT_LITERAL ")" | "result" | "member" "(" path ")" | "component" "(" INT_LITERAL ")";

# Generated audited native contracts; scope/value consistency is checked semantically.
ffi_contract ::= "ffi-contract" "{" ffi_clause* "}";
ffi_protocol ::= "ffi-protocol" path "=" STRING_LITERAL ";";
ffi_clause ::= ffi_property "=" ffi_value ";" | ffi_subject "{" ffi_clause* "}";
ffi_subject ::= semantic_selector | "pointer" | "output" | "callback" | "marshalling";
ffi_property ::= "invocation" | "blocking" | "finite-return" | "native-cancellation" | "foreign-unwind" | "ownership" | "retention" | "mutability" | "aliasing" | "stable-address" | "provenance" | "initialization" | "failure-state" | "lifetime" | "cardinality" | "reentrancy" | "thread-affinity" | "delivery-domain" | "barrier" | "suspension" | "algebraic-crossing" | "cancellation" | "defect" | "pending-defect-entry" | "deregistration" | "drain" | "undelivered" | "shutdown" | "preconditions";
ffi_value ::= IDENT | capture_bound | "protocol" "(" path ")";
```
<!-- END GENERATED ELDUDE GRAMMAR -->

