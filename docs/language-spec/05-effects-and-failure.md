# Chapter 5 — Effects, termination, and failure

[Specification index](../language-specification.md) · Previous: [4. Closures, captures, and scoped access](04-captures-and-access.md) · Next: [6. Handlers and resumption](06-handlers.md)

This chapter describes visible behavior, conservative non-divergence checking, and expected failure as ordinary data.

**Prerequisites:** [1. Foundations and programs](01-foundations.md), [4. Closures, captures, and scoped access](04-captures-and-access.md).

The numbered rules are normative under the [specification conventions](../language-specification.md). Examples are illustrative snippets; names and omitted bodies may stand for surrounding program or library context.

An empty row is interpreted alongside parameter access modes; `mut` carries supplied state authority ([§14.3](04-captures-and-access.md#143-mut)). A contract without `diverge` still permits defect termination or structural cancellation ([§19.1](#191-default-contract)).

## B.2 Effect-polymorphic higher-order function

```eldude
fn apply<A, B, !e, ..C>(
    f: fn(A) ->{| e} B captures {..C},
    value: A,
) ->{| e} B {
    f(value)
}
```

The callback is invoked exactly once, so no `Dup`/`Discard` constraint on `..C` is needed solely for invocation multiplicity.

## In this chapter

- [16. Effect rows](#16-effect-rows)
- [17. User-defined algebraic effects](#17-user-defined-algebraic-effects)
- [18. Intrinsic semantic effects](#18-intrinsic-semantic-effects)
- [19. Non-divergence](#19-non-divergence)
- [20. Defects and assertions](#20-defects-and-assertions)
- [21. Expected failure and nominal error composition](#21-expected-failure-and-nominal-error-composition)
- [22. Diagnostics and logging](#22-diagnostics-and-logging)

## 16. Effect rows

### 16.1 Function effect syntax

Function arrows may carry effect rows:

```eldude
fn(A) -> B
fn(A) ->{fs} B
fn(A) ->{fs, diverge} B
fn(A) ->{| e} B
fn(A) ->{fs | e} B
```

The empty row is omitted.

Rows are scoped upper bounds: a finite sequence of fixed effect entries followed by at most one open tail. Different entries commute; repeated equal entries are retained as distinct slots, so `{E, E}` is not equal to `{E}`. For an algebraic family, those slots allow separate handler layers of the same applied family. They do not count how many times an operation executes. Repeated calls through one instance use the same slot.

The only open forms are `{| e}` and `{E1, E2 | e}`. The tail must be a declared effect-row parameter or an inference variable in the elaborated core. A row parameter cannot occur among fixed entries: `{e}` and `{E, e}` are ill-kinded when `e` is a row parameter. `{E | e, f}`, multiple tails, and arbitrary row-union expressions are not part of the language. Closed rows may have a trailing comma; an open tail is always the final item without a trailing comma.

Effect weakening admits a computation in a larger ambient row by preserving its existing effect slots and adding unused slots. It never retargets a lexically named instance. This is distinct from row equality: no equality rule deletes duplicates. The restricted inference/checking rules are in [§16.5](#165-scoped-row-equality-inference-and-weakening); arbitrary effect-subtyping constraints are not exported in function types.

For a callable with `mut` parameters or receiver, the written row is interpreted under the supplied access authority ([§14.3](04-captures-and-access.md#143-mut)). The complete effects of a call also include state charges for root grants formed at that call ([§59.3](11-formal-semantics.md#593-access-modes)); an empty written row alone does not make such a root invocation pure.

### 16.2 Effect-row polymorphism

An effect-row parameter is declared with `!`:

```eldude
fn apply<A, B, !e>(
    f: fn(A) ->{| e} B,
    value: A,
) ->{| e} B;
```

After the row-tail separator, the variable is written `e`, not `!e`. Several computations combined by one function normally share an ambient row parameter, rather than introducing independent tails and an expression that unions them. For example:

```eldude
fn both<!e>(left: fn() ->{| e} Unit, right: fn() ->{| e} Unit) ->{| e} Unit {
    left();
    right()
}
```

Closed callback rows such as `{Console}` and `{Fs}` may each weaken to the common `{Console, Fs}` at a call. This does not require the callbacks to perform the same effects. A generic function body's explicitly bound `e` is rigid; it is instantiated freshly only at a use of that polymorphic function.

### 16.3 Effect categories

Eldude distinguishes three semantic categories of row entry.

**Algebraic effect families** are declared with `effect` and may be interpreted by handlers.

An algebraic row entry is the family identity applied to all its declared generic arguments, for example `Store<Int>` or `Raise<LoadError>`. These arguments are fixed for each effect instance ([§17.4](#174-effect-instances)), not freshly universally quantified on each operation call. Distinct applications such as `Store<Int>` and `Store<Text>` are distinct row entries and may coexist. Open effect-row variables occur only after `|`. The contextual application `state<@r>` denotes the intrinsic region-state entry below, not a user-handleable family.

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

For updates through call-scoped `mut` access, the root invocation accounts for region state and the supplied grant carries that authority into callees ([§14.3](04-captures-and-access.md#143-mut)). Forwarding or projection does not erase the original charge, and independent state operations retain ordinary row accounting.

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

### 16.5 Scoped-row equality, inference, and weakening

The row fragment uses fixed entries and one tail. Row equality is equality modulo exchange of distinct entries, preserving multiplicity. Effect-family arguments first undergo ordinary type/index/region normalization. Label comparison uses the resulting applied family and any lexically fixed instance identity; unresolved arguments cannot be guessed by choosing among different effect applications. Such a choice is postponed until ordinary inference fixes it, or requires an annotation if still ambiguous. This row fragment does not promise principal inference for Eldude's entire higher-rank, trait, capture, or usage system.

Unification follows these finite rules:

1. Expand already-solved tails, then cancel matching fixed entries one occurrence at a time.
2. Equal remaining prefixes and the same tail succeed. Unequal prefixes over the same tail fail; solving `e = {E | e}` would require an infinite row.
3. An otherwise unconstrained flexible tail may be bound to the unmatched prefix and tail on the opposite side, subject to an occurs check. A closed row cannot acquire entries, and a rigid generic tail cannot be assigned.
4. With unmatched entries on both sides and two distinct flexible tails, introduce one fresh shared tail. For example, `{E | a} = {F | b}` yields `a = {F | c}` and `b = {E | c}`. If either required extension is closed or rigid, equality fails.

Thus `{E | e} = {E}` has only `e = {}`, while `{E | e} = {E, E}` has only `e = {E}`. No lacks constraints, presence flags, or arbitrary unions of independent tails are required by this equality fragment.

Sequencing, branches, arguments, callback invocation, root state grants, and child-effect accounting check against a **common ambient row**. They do not concatenate the rows of executed operations. At permitted value-use/callback adaptation sites, a closed row may be opened with a fresh flexible tail and unified with the expected ambient row. Instantiation of a polymorphic callable similarly introduces fresh flexible tails. Function contracts are checked before this adaptation; weakening cannot justify undeclared effects inside a definition.

With a rigid tail, weakening may insert known fixed slots while preserving that same tail and the identity/order of every retained slot. For example, `{| e}` may be used under `{state<@r> | e}`. Closed-row weakening similarly inserts known slots. This directed check does not solve a union or inequality between distinct rigid tails. If a combined computation cannot be described with one shared tail using these rules, require a shared-row signature or an explicit compatible contract; do not export a hidden set-union/subeffect constraint. Ordinary type variance, capture, usage, `NonAbandoning`, and scope checks still apply to any callable adaptation.

Repeated requirements for one already-selected instance or one intrinsic state/suspension/divergence slot reuse that ambient slot. Different selected handler instances retain separate slots even when their printed family names coincide. Intrinsic duplicates add no new runtime behavior, but remain distinct in row equality and serialization; effect weakening must not be confused with equality or used to erase a required slot.

Lexical handler selection supplies the evidence for each algebraic slot. An unqualified call selects the nearest eligible slot; a named call keeps its selected lexical identity through weakening and abstraction. Same-family slots are ordered nearest-to-outer in the evidence, even though their printed labels are identical. A handler removes only its own slot. For example, handling the inner `E` of `{E, E | e}` leaves `{E | e}`. Clause checking has explicit `self` access to the current instance ([§26.4](06-handlers.md#264-same-family-operations-inside-clauses)), plus the residual ambient row. Its outward effects, including forwarding, must fit that residual row; an outer `E` requirement cannot disappear with the inner delimiter. Canonical interfaces preserve multiplicities and every lexically fixed instance relationship needed by clients ([§72](12-interfaces-and-tooling.md#72-canonical-semantic-interfaces)).

The executable prototype in `python-impl/src/eldude/core/rows.py` checks this row-equality fragment and closed-row opening on already-resolved label keys. Its tests cover distinct applied families, named-instance keys, repeated calls, nested layers, forwarding, rigid tails, and infinite-row rejection. It is not an Eldude expression/type checker and does not validate evidence selection, type-argument inference, or ownership. The design follows Koka's [row-polymorphic effect inference](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/paper-20.pdf), adapted to Eldude's lexical instance and resource contracts.

The separate, non-normative experiment in [`python-impl/src/eldude/core/inference.py`](../../python-impl/src/eldude/core/inference.py) layers annotated expression inference over that solver. Its [cases](../../python-impl/tests/core/test_inference.py) cover effectful traversal, nested same-family instance selection, scoped references, cancellation checks with owned resources, and a serialized `DynArray::freeze` wrapper contract. The [implementation guide](../implementation.md#inference-experiment) records the results and supported fragment. It does not implement Eldude source checking, handler clauses/resumptions, or runtime evidence passing.

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

Family generic parameters scope over every operation signature and are instantiated once for the selected instance. For example:

```eldude
fn raise<E>(error: E) ->{Raise<E>} Never {
    !Raise::<E>::raise(error)
}
```

An operation has no operation-local generic binder in this version. Explicit dispatch arguments use `!Family::<Args>::operation(...)`; a named instance already fixes its family arguments and uses `!instance::operation(...)` without repeating them.

### 17.2 Resumption modes

The core modes are normative:

```text
tail
    automatic exactly-once resumption with the clause's result, as its final semantic action

once
    exactly one resume; the clause may regain control afterward

affine
    zero or one resume
```

The declaration describes control behavior independently of the handler implementation. Many-shot resumption is not part of the core and is listed as deferred in [Appendix A](scope-and-deferrals.md#appendix-a--deliberately-absent-or-deferred-features).

### 17.3 Derived continuation-control envelope

Effect rows determine a compiler-derived continuation-control envelope used at opaque calls and other composition boundaries. In the core, the envelope records whether evaluation may abandon the surrounding continuation. The envelope is evaluated relative to the current structural-control context `Control`, including whether cooperative cancellation is masked at the evaluation point.

For a closed effect row `Effects`, define `mayAbandon(Control, Effects)` as follows:

- `suspend` contributes an abandonment path exactly when cooperative cancellation is **not** masked by `Control`, because an actual unmasked suspension point may deliver cancellation;
- an algebraic effect family contributes an abandonment path when it declares at least one `affine` operation that can escape the relevant boundary; structural cancellation masking does not neutralize algebraic abandonment;
- `tail`, `once`, `diverge`, and `state<@r>` do not by themselves contribute an abandonment path.

In the ordinary unmasked structural control context `UnmaskedControl`, write `mayAbandon(Effects)` as shorthand for `mayAbandon(UnmaskedControl, Effects)`. An unconstrained open effect-row variable is conservatively treated as potentially abandoning in any context where its unknown families could contain `affine`; masking may remove only the known cancellation edge contributed by `suspend`.

Eldude exposes exactly one source constraint on the **ordinary unmasked** derived property:

```eldude
where e: NonAbandoning
```

`NonAbandoning` is an intrinsic compiler-governed predicate over effect rows, not a trait, effect family, capability, or user-implementable protocol. A closed row satisfies it exactly when `mayAbandon(UnmaskedControl, Effects)` is false. An open row variable satisfies it when its generic constraint environment contains `e: NonAbandoning`; every substitution for that variable MUST itself satisfy the predicate. For a compound row such as `{state<@r> | e}`, the whole row is checked compositionally.

Thus generic code may quantify over unknown ordinary effects while ruling out continuation abandonment. A structural mask can make a particular execution context less abandoning than the row's unmasked contract without changing whether the row itself satisfies `NonAbandoning`.

At an ordinary call `f(...)` with admitted row `Effects`, the checker evaluates `mayAbandon(Control, Effects)` in the current structural context. If it holds, every continuation segment that may be abandoned must be a legal structural exit under [§62.2](11-formal-semantics.md#622-non-local-exit-judgment). Handling an algebraic instance locally removes only its selected slot from the residual row. Outer slots of the same family continue to contribute to the downstream envelope. The envelope is derived from effect declarations and existing structural masks already represented in `Control`; it is not another user-defined capability or effect axis.

Canonical cleanup and taskgroup-shutdown execution establish cancellation masks in `Control`. The same envelope rule therefore explains why `suspend` is non-abandoning *in those masked contexts* while residual `affine` control remains abandoning. No cleanup-specific or shutdown-specific effect classification exists.

### 17.4 Effect instances

At elaborated-core level, an algebraic operation belongs to a fully applied effect family plus an instance identity. `handler Store<Int>` introduces an instance whose operation signatures are substituted with `T = Int`. The handler must supply every family argument, either explicitly or by ordinary local inference; unresolved family arguments are errors. A canonical interface always renders the complete application.

A `handle` expression creates a fresh instance for its inline lexical handler. Source code may name it when necessary:

```eldude
handle {
    !console::print("hello");
} with console = handler Console {
    print(text) => terminalWrite(text);

    readLine() => {
        resume(terminalRead());
    }
}
```

An unqualified operation such as:

```eldude
!Console::print(...)
```

selects the nearest unambiguous ambient instance of that applied family. For a generic family, omitted arguments must be determined by its current effect contract, ordinary argument/result inference, or a unique ambient application; they are not guessed from handler implementation bodies. An explicit application selects the nearest instance of that same application, so an inner `Store<Int>` does not intercept `Store<Text>`. Distinct named instances of the same application retain distinct lexical identities in the elaborated row and capture metadata. Ambiguity is an error.

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

The compiler MUST accept recursion satisfying the following structural rule over finite inductive declarations of [§8.5](02-types-and-ownership.md#85-finite-inductive-recursive-declarations). In each mutually recursive function group, choose a common ordered vector of designated inductive parameter positions (one position is sufficient for ordinary list/tree recursion). At every call edge within the group, the argument vector must be lexicographically smaller: preceding components preserve the incoming component, one component is a proper stored subterm of its corresponding incoming component, and later components are unrestricted. The compiler checks the finite set of possible position vectors. Recursion outside this structural rule admits `diverge` under [§19.3](#193-conservative-proof-boundary).

The structural-subterm relation is generated only by constructor decomposition of a known inductive value, including visible data-field reads of those same stored components ([§8.1](02-types-and-ownership.md#81-products)): each actually stored field/payload reached through finite positive storage positions is a direct subterm, and paths with at least one such decomposition are proper subterms. Pattern-derived equalities and non-consuming copies preserve the same relation; simple name aliases preserve it as well. Nested patterns compose paths. Matching a GADT may change indices without changing this stored-subterm fact.

Reconstruction, arbitrary function results, associated-type equalities alone, calls through stored functions, reads from mutable/foreign identities, and unspecified container accessors establish no structural-subterm relation. A new value equal by `Eq` to a child is not thereby a tracked child. Pattern inspection observes the same runtime constructor but still obeys the ownership rules of [§8.4](02-types-and-ownership.md#84-pattern-matching); termination evidence never grants duplication, discard, or access permissions. Imported bodies are not inspected to discover subterm relationships.

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

### 19.3 Conservative proof boundary

The initial core establishes non-divergence using structural recursion ([§19.2](#192-structural-recursion)), certified finite iteration ([§35.5](08-collections.md#355-finite-iteration-and-non-divergence)), and the declared contracts and control-dependency checks of [§§19.6](#196-elaborated-control-dependency-graph)–[19.8](#198-external-operations). Other recursion contributes `diverge`. Arithmetic results such as `n - 1` or `a % b` are not stored subterms, even when a programmer can prove numeric descent.

Symbolic `decreases` annotations and arithmetic termination proofs are deferred; they are not part of the source or canonical-interface grammar. Stronger private arithmetic reasoning or optimization MUST NOT erase `diverge` required by these rules. Adding a measure language requires a specification change.

For example, Euclid's algorithm must admit `diverge` in the initial core:

```eldude
fn gcd(a: Nat, b: Nat) ->{diverge} Nat {
    if b == 0nat {
        a
    } else {
        gcd(b, a % b)
    }
}
```

The row conservatively describes what the checker can establish. A caller must also admit `diverge`; a written non-diverging contract for this definition is rejected.

### 19.4 `while`

Every `while` loop contributes `diverge` in the initial core, in addition to the effects of its condition and body. Literal conditions and an immediate exit do not remove this conservative requirement. Code requiring a non-diverging contract can use structural recursion or certified finite iteration when applicable.

### 19.5 `for`

A `for` loop may omit `diverge` only when the selected iterator implementation is certified finite under [§35.5](08-collections.md#355-finite-iteration-and-non-divergence) and source evaluation, iteration steps, the body, and structural discharge are non-diverging under their ordinary contracts.

Without that finite-iteration fact, the loop contributes `diverge`. An apparent numeric bound or an expected early `break` does not certify an otherwise unbounded source.

### 19.6 Elaborated control-dependency graph

Termination checking is not limited to syntactic recursion.

The compiler constructs or approximates an elaborated control-dependency graph containing relevant edges from:

- direct function calls;
- higher-order callable invocation;
- callable loads/stores through mutable state;
- algebraic operations and handler clauses;
- explicit and implicit resumption;
- explicit `!self` control cycles;
- forwarded effect paths;
- task-completion dependencies introduced by `await` or taskgroup drain;
- other control transfers capable of forming a semantic cycle.

Any strongly connected dependency whose termination is not established by the permitted structural or finite-iteration rules contributes `diverge`. Declared callable effect rows alone cannot discharge a cycle through mutable state, handlers, or tasks.

Unknown control dependencies conservatively contribute `diverge`; the absence of direct source recursion is not termination evidence.

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

A direct local await of a known non-diverging child may require only `suspend`. Local producer provenance and acyclic dependency information may establish this under the same conservative rules; separate clients do not inspect that body. The initial architecture prefers conservative `diverge` rather than requiring canonical termination-dependency summaries; such summaries may be added later only if concrete programs justify the extra interface machinery.

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

The explicitly specified arithmetic and initialization defects ([§§6.1.1](02-types-and-ownership.md#611-primitive-operator-typing-and-evaluation) and [5.2](01-foundations.md#52-declaration-only-top-level)) use this same boundary and precedence rule. They are not additional recoverable failure mechanisms.

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

## B.14 Assertions

```eldude
fn internalInvariant(x: State) -> Unit {
    assert x.valid();
}
```

Assertion failure is a defect; it is not represented in the function's effect row or as `Result`.

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

Eldude has no structural `error { ... }` type and no implicit nominal-error subtyping/widening. When a computation with error type `E1` must participate in an API using error type `E2`, the program performs an explicit mapping or constructs the chosen nominal variant.

This keeps expected failure within the ordinary nominal data model rather than introducing a specialized structural sum mechanism.

### 21.3 Postfix `?`

For:

```eldude
expr?
```

`expr` is evaluated exactly once and must produce `Result<E,T>` compatible with the nearest lexical propagation target.

On `Ok(value)`, the expression yields `value`.

On `Err(error)`, control transfers to the nearest lexical `try` boundary within the current function/result boundary using the **same nominal error type `E`**; if none exists, the current function returns `Err(error)` and its declared result must use that same `E`. A `tail` operation clause is its own result boundary under [§25.2](06-handlers.md#252-tail): propagation cannot reach an enclosing function or an outer `try`.

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

`return` inside a `try` still targets the enclosing function or tail-clause result boundary; it does not target the `try` itself.

### 21.6 Optional access and coalescing

For `Option<T>`, optional member access uses `.?`:

```eldude
user.?address.?city
```

It does not implicitly flatten nested `Option` values.

For data fields, if `option: Option<T>` and visible field `field: F` belongs to `T`, `option.?field` has type `Option<F>` and MUST require `F: Dup`. It preserves a bound `option` and its payload: `None` yields `None`, and `Some(value)` yields `Some` of a copy of the field. If `F` is itself an `Option<U>`, the result is `Option<Option<U>>`. The receiver is evaluated once; a computed owned temporary additionally requires `Option<T>: Discard`, exactly as for ordinary field projection ([§8.1](02-types-and-ownership.md#81-products)). No field or payload ownership is extracted by this syntax.

Coalescing:

```eldude
option ?? fallback
```

evaluates `fallback` only for `None`.

## B.13 Typed failure with explicit nominal mapping

```eldude
enum LoadError {
    IO(IOError),
    Parse(ParseError),
}

fn load(path: Path) ->{fs, diverge} Result<LoadError, Config>
{
    let bytes =
        readFile(path).mapError(LoadError::IO)?;
    parse(bytes).mapError(LoadError::Parse)
}
```

`?` propagates only the chosen nominal error type. Different nominal errors require explicit mapping.

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

---

[Specification index](../language-specification.md) · Previous: [4. Closures, captures, and scoped access](04-captures-and-access.md) · Next: [6. Handlers and resumption](06-handlers.md)
