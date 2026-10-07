# Chapter 1 — Foundations and programs

[Specification index](../language-specification.md) · Next: [2. Types and ownership](02-types-and-ownership.md)

Start here for the semantic vocabulary, source model, evaluation order, functions, and module boundaries.

**Prerequisites:** none; the [manifesto](../index.md#the-eldude-manifesto) supplies the design motivation.

The numbered rules are normative under the [specification conventions](../language-specification.md). Examples are illustrative snippets; names and omitted bodies may stand for surrounding program or library context.

## B.1 Pure non-diverging function

```eldude
fn add(x: Int, y: Int) -> Int {
    x + y
}
```

## In this chapter

- [1. Semantic dimensions](#1-semantic-dimensions)
- [2. Surface and parsing model](#2-surface-and-parsing-model)
- [3. Evaluation](#3-evaluation)
- [4. Functions and calls](#4-functions-and-calls)
- [5. Modules and top-level structure](#5-modules-and-top-level-structure)

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

The source grammar reserves the following words because they participate directly in Eldude syntax:

```text
affine any as assert await break captures case const continue
effect else enum extern false fn for forall forward handle handler if impl
import in intrinsic let linear match module mut once pub region resume return self spawn
struct suspend taskgroup trait true try type unsafe using view where while
diverge
```

`with`, `tail`, and `state` are contextual words: they introduce handler composition, tail-resumption declarations, and region-state row entries in those specific grammatical positions, and are ordinary identifiers elsewhere. This permits projection APIs named `with`, record fields named `tail`, and values named `state` without name-dependent parsing.

`many`, `abort`, `error`, and `host` are not reserved words. Many-shot resumption is deferred; abortive operations are expressed by `affine ... -> Never`; expected-error composition uses nominal enums; host selection is root/build metadata rather than source syntax. Primitive type names such as `Int`, `Bool`, and `Unit` are ordinary predefined type names rather than keywords.

The category sigils are context-free tokens:

```text
!e     effect-row generic parameter declaration
@r     region identity/reference
#N     compile-time-natural generic parameter declaration
..C    capture-row parameter/rest
```

At expression level, `!Qualified::op(...)` is algebraic operation dispatch. `!` is not an ordinary general-purpose prefix operator. This prevents `!Console::check()` from having a second parse as boolean negation of an ordinary call.

Lexing uses longest-token matching for multi-character punctuation, including at least:

```text
::  ->  =>  .?  ??  ..  ==  !=  <=  >=
```

Turbofish is parsed as `::` followed by `<...>`; it is not a distinct semantic token. Nested generic closers are individual `>` tokens; Eldude defines no `>>` shift operator.

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

The normative grammar is context-free and defined by [eldude.ebnf](../eldude.ebnf), published in the standalone [formal grammar](../formal-grammar.md). The following disambiguation rules are part of that contract:

- `value.method(args)` selects a consuming/value receiver (`self`);
- `view value.method(args)` selects `view self`;
- `mut value.method(args)` selects `mut self`;
- `view`/`mut` access arguments and access-prefixed method receivers apply to an in-scope binding (including a callback parameter carrying a projected grant), not to an arbitrary computed expression; compute an expression into a binding first when access must be granted to its result;
- this binding-only rule keeps `f(view x.method())` unambiguous: it is a plain argument whose expression is the `view self` method call, while `f(view x)` is an ordinary `view` argument;
- the parser chooses among the three method forms syntactically, before method lookup; the type checker later verifies that the selected method has the matching receiver mode;
- `!path::op(args)` is always algebraic operation dispatch; explicit family arguments use `!path::<Args>::op(args)`, with the same expression-level turbofish convention as ordinary generic application;
- `@name`, `#name`, `!name` in generic-parameter lists, and `..name` in capture-row positions are determined solely by grammatical context;
- an effect row has fixed entries followed by at most one `| name` tail; `{| e}` is tail-only, and `{E | e}` extends that tail. Whether a fixed entry denotes an effect family rather than a row variable is checked by kinding, not parsing;
- `semantic { ... }` is not ordinary source syntax; it belongs to the `interface_file` entry point of the normative grammar;
- an unparenthesized nominal construction is excluded from the outer condition/scrutinee/source expression of `if`, `while`, `match`, and `for`; parentheses permit it and prevent confusion with the following block;
- `await` and `spawn` take the immediately following unary/postfix operand; use parentheses or a block to group a larger computation;
- an undelimited `=>` lambda body and the operand of `return` consume the longest following expression permitted by the enclosing grammatical delimiters. Among complete derivations, compare those body/operand end-token positions in order of their introducing `=>`/`return` tokens, earliest first, and choose the lexicographically greatest vector. Thus `fn(x) => x + 1` keeps the addition inside the lambda and `return f() + 1` returns the sum. Parenthesize the lambda/return expression when a following postfix/binary operation belongs outside it, as in `(fn(x) => x)(1)`;
- a capture clause attaches to the nearest unparenthesized function contract; parenthesize a returned function type before writing a capture clause for the outer function;
- a generic closing `>` immediately followed by `=` forms the longest token `>=`; separate them with whitespace when a closing delimiter and equality/initializer token are intended.

### 2.9 Lexical payloads and consolidated forms

Source is UTF-8. Identifiers use ASCII letters/underscore followed by ASCII letters/digits/underscores; capitalization does not create a second token category. Reserved words cannot be identifiers. `//` comments end at a newline or end of file; `/* ... */` comments are non-nesting. Whitespace/comments separate tokens except within literals. Numeric token forms are those of [§6.1.3](02-types-and-ownership.md#613-numeric-literals-and-defaulting) and the artifact.

Double-quoted strings contain Unicode scalar values. Single-quoted character literals contain exactly one scalar value. Raw control characters U+0000–U+001F, unescaped delimiters/backslash, and literal newlines are excluded. Escapes are `\n`, `\r`, `\t`, `\0`, `\\`, `\"`, `\'`, and `\u{H}` with one to six hexadecimal digits representing a Unicode scalar value. Invalid scalar escapes are rejected. There are no raw, multiline, interpolated, or byte-string literal forms. String literals have type `Text`; character literals have type `Char`.

Anonymous function parameters may omit a type when ordinary inference or an expected function type supplies it, as in `fn(x) => x`. Named-function parameters are typed; receiver `self` uses its enclosing implementation/trait type. `forall<...>. Type` is the explicit higher-rank type form. An associated projection may use `T::Item` when its trait is unambiguous in the static contract, or `<T as Trait<Args>>::Item<GatArgs>` for explicit qualification. This is type syntax, not expression-level conversion.

Enum variants may use tuple payloads or nominal record payloads, for example `Cons { head: T, tail: LinkedList<T> }`; that record belongs to the enum constructor and is not a structural record type. Construction and patterns use `LinkedList::Cons { head, tail }`. All fields of an owned product/record pattern must be explicit, including wildcards; there is no rest pattern. Every nonfinal expression, including `while` and `for`, requires a terminating semicolon. A final loop expression may omit it and yields `Unit`. Thus `{ while condition {} ; -1 }` has an integer tail; without the separator, `{ while condition {} -1 }` is one subtraction expression and fails typing because its left operand is `Unit`.

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

`break` has no result value in the current design; loops have type `Unit` unless another expression form explicitly provides a result. Branch ownership joins and loop header/back-edge/exit rules are normative in [§§62.5](11-formal-semantics.md#625-usage-environments-and-branch-joins)–[62.6](11-formal-semantics.md#626-loop-headers-back-edges-and-exits).

Every non-local control exit that continues Eldude execution elsewhere uses the single obligation-discharge judgment of [§62.2](11-formal-semantics.md#622-non-local-exit-judgment). Defects use [§20](05-effects-and-failure.md#20-defects-and-assertions)'s nonrecoverable boundary and structural unwinding instead. Feature-specific rules below specify what each structural owner discharges, not alternative exit-legality tests.

A `tail` operation clause introduces a local result boundary ([§25.2](06-handlers.md#252-tail)). A `return` in that clause returns its operation result for automatic resumption; it does not return from the function containing the handler. Nested functions have their ordinary separate return boundaries.

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

Top level contains declarations only. An import establishes a static dependency; it does not execute code at its textual position. Ordinary top-level values are initialized once during the root startup phase defined below.

Every ordinary top-level `let` initializer MUST be pure and terminating, and its result type MUST satisfy `Dup + Discard`. This applies to private as well as exported bindings and is checked using the ordinary structural usage rules, including obligations retained by closures, opaque values, and erased packages.

A module binding is a reusable definition, not a globally tracked affine or linear owner. For example:

```eldude
linear struct Token;

let token = Token {};                 // invalid: Token is not Dup + Discard
let makeToken = fn() => Token {};     // valid: the capture-free factory is Dup + Discard
```

A factory may return a fresh ownership obligation on each invocation; the restriction concerns the value held by the top-level binding. Runtime startup and ownership of state/resources belong to the selected host/root lifecycle or explicit state abstractions created during runtime execution.

The selected root initializes all modules in its transitive import closure before entering application code or exposing embedding entry points. Primitive/predefined values and named declaration identities are available first. To order module initializers, collapse the import graph's strongly connected components and visit dependencies before importers; when several components are ready, choose the one whose smallest member path is lexicographically first. Within a component, visit modules by canonical path; within a module, evaluate top-level `let` initializers in source declaration order. Re-exports introduce ordinary import dependencies. Modules containing only declarations without value initializers have no executable initialization step.

Each binding becomes available only after its initializer returns normally. Reading a not-yet-initialized top-level binding is an explicit nonrecoverable initialization defect, including a read through a function or callback. It does not trigger on-demand evaluation, retry, or waiting. This rule gives forward reads and cyclic imports a defined outcome without inspecting imported bodies or adding an initialization-effect axis. The first initializer defect stops startup, performs the ordinary structural unwinding, and reaches the root's defect boundary; later initializers and the application root do not run. An unused binding is still initialized.

An implementation MAY precompute initializers or omit unobservable work only when it preserves this startup behavior, including defect order. A defect discovered by precomputation remains a startup defect, not an implementation-dependent source rejection. Initializers are checked with all named declarations in scope, so declaration visibility and initialization availability are distinct. Initializer code receives no general access to runtime services beyond its checked empty effect row.

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

A public trait's methods and associated declarations, and a public effect's operations, are all part of its visible contract; individual visibility modifiers there are invalid. Implementation methods inherit the trait method's visibility and cannot alter it. Implicit trait implementations have no `pub` modifier: their applicable headers are exported in the canonical index under [§§10](03-traits.md#10-traits) and [72.4](12-interfaces-and-tooling.md#724-trait-implementation-index) even though their bodies remain private. Inherent methods use ordinary explicit `pub`.

An ordinary import creates private local names. `pub import path::{Name, Other as Alias};` additionally re-exports those names/aliases and is permitted only for already public entities. A re-export preserves the defining identity, ownership, and opacity; it does not reveal private members. Qualified lookup across a module boundary observes the same visibility rules as importing. No wildcard import or implicit re-export exists.

Every nominal/trait/effect identity appearing in a public author-visible contract must itself be publicly nameable, directly or through a public re-export. Private representation fields may contain private identities, provided canonical usage, positivity, captures, and other client-required guarantees are still exported without granting representation access. Public associated equations and method signatures cannot expose private nominal identities. Visibility never exempts the compiler from canonical interface completeness.

Exhaustiveness accounts for hidden enum variants using an opaque remainder. Outside the defining module, if any variants are hidden, a match requires a wildcard or name catch-all for that remainder; an owned wildcard still requires `Discard`, while a name transfers ownership ([§8.4](02-types-and-ownership.md#84-pattern-matching)). Interfaces reveal that a hidden remainder exists without exporting its constructors. Eldude has no `some Trait` abstraction form.

Generated interfaces mark an incomplete representation with `representation = opaque` under [§72.7](12-interfaces-and-tooling.md#727-human-readable-semantic-interface-rendering). On a partially visible enum this is the hidden-remainder fact; on a struct it prevents clients from treating the listed fields as a complete construction/decomposition. This single completeness marker does not reveal omitted member identities.

### 5.4 Public contracts

Canonical exported contracts MUST contain every semantic fact required by clients: types, effects, effect-row constraints such as `NonAbandoning`, captures, usage guarantees, regions, generic naturals, trait requirements, handler residuals, cleanup facts, and relevant ABI/foreign semantic contracts. Application or embedding roots additionally carry the separate root-only host/embedding contract of [§48.4](10-host-and-ffi.md#484-root-and-embedding-contracts).

Private implementation bodies are not part of ordinary downstream semantic checking.

---

[Specification index](../language-specification.md) · Next: [2. Types and ownership](02-types-and-ownership.md)
