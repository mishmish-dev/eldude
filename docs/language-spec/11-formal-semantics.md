# Chapter 11 — Formal static and dynamic semantics

[Specification index](../language-specification.md) · Previous: [10. Host, unsafe code, and FFI](10-host-and-ffi.md) · Next: [12. Interfaces, compilation, and tooling](12-interfaces-and-tooling.md)

This implementer reference gives checking judgments, the dynamic machine, and soundness obligations for the language contracts.

**Prerequisites:** [1. Foundations and programs](01-foundations.md), [2. Types and ownership](02-types-and-ownership.md), [3. Traits and dynamic abstraction](03-traits.md), [4. Closures, captures, and scoped access](04-captures-and-access.md), [5. Effects, termination, and failure](05-effects-and-failure.md), [6. Handlers and resumption](06-handlers.md), [7. Regions, mutable state, and cleanup](07-state-and-cleanup.md), [8. Collections and iteration](08-collections.md), [9. Structured concurrency](09-concurrency.md), [10. Host, unsafe code, and FFI](10-host-and-ffi.md).

The numbered rules are normative under the [specification conventions](../language-specification.md). Examples are illustrative snippets; names and omitted bodies may stand for surrounding program or library context.

For a literal, the combined judgment has no effects or retained obligations:

```text
TypingEnvironment ; Regions ; Handlers ; Taskgroups ; Usage ; Access ; Control
    ⊢ 42 : Int ! {} ▷ {}
```

The judgments below describe the same contracts as the language chapters. The common control-exit judgment is [§62.2](#622-non-local-exit-judgment); feature rules identify the obligations it must discharge.

## In this chapter

- [58. Static contexts and judgments](#58-static-contexts-and-judgments)
- [59. Function introduction and application](#59-function-introduction-and-application)
- [60. Capture soundness](#60-capture-soundness)
- [61. Region typing](#61-region-typing)
- [62. Usage and control exits](#62-usage-and-control-exits)
- [63. Cleanup typing](#63-cleanup-typing)
- [64. Algebraic operation and handler typing](#64-algebraic-operation-and-handler-typing)
- [65. Captured continuation segment](#65-captured-continuation-segment)
- [66. Error typing](#66-error-typing)
- [67. Task typing](#67-task-typing)
- [68. Taskgroup dynamic obligations](#68-taskgroup-dynamic-obligations)
- [69. Dynamic machine](#69-dynamic-machine)
- [70. Soundness obligations](#70-soundness-obligations)

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

for effect rows whose **ordinary unmasked** continuation-control envelope cannot abandon the surrounding continuation. For a closed row this holds exactly when `mayAbandon(UnmaskedControl, Effects)` from [§17.3](05-effects-and-failure.md#173-derived-continuation-control-envelope) is false. For an open row variable `e`, the judgment holds only when the constraint environment contains `e: NonAbandoning`. Generic substitution for such a variable is valid only when the substituted row satisfies the same judgment.

The judgment is compositional over a row prefix and its optional single tail: every fixed entry and the tail must be non-abandoning for the complete row to satisfy it. `NonAbandoning` is compiler-governed and has no user `impl` form.

Static control checking also uses the context-relative helper `mayAbandon(Control, Effects)` from [§17.3](05-effects-and-failure.md#173-derived-continuation-control-envelope). Structural masking is represented by `Control`; it may remove the cancellation edge contributed by `suspend`, but it does not grant `NonAbandoning` to the row itself and does not neutralize unknown or explicit algebraic `affine` behavior.

### 58.6 Dynamic-interface judgments

Representative judgments are:

```text
StaticEnvironment ⊢ PackageInterface : DynInterface
StaticEnvironment ; PackageInterface ⊢ Method : DynMethod
```

where `PackageInterface` is an `any Trait<...>` package interface after visible trait arguments and associated-type equalities have been supplied. `StaticEnvironment ⊢ PackageInterface : DynInterface` holds exactly when the package is well-kinded and every trait method satisfies `StaticEnvironment ; PackageInterface ⊢ Method : DynMethod`.

`StaticEnvironment ; PackageInterface ⊢ Method : DynMethod` is the algorithm of [§11.2](03-traits.md#112-dynamic-compatibility): substitute package-visible trait arguments and ordinary associated types; reject method-local generic parameters, raw `Self` outside the receiver, every GAT projection, unresolved associated projections, constraints not derivable from `PackageInterface`, and any effect/result-capture contract that mentions hidden concrete-type information. The judgment depends only on canonical interface data.

Packaging a concrete value `value: ConcreteType` as `PackageInterface` additionally requires:

- `ConcreteType` satisfies the trait implementation represented by `PackageInterface`;
- the concrete implementation's associated types agree with every equality advertised by `PackageInterface`;
- all advertised `Dup`/`Discard` guarantees hold;
- the package preserves the value's tracked capture/provenance and any mutable-owner status required by the erased interface.

A dynamic method invocation uses the already-substituted public method contract from `PackageInterface`, including its effect row and result-capture bound. It does not inspect the hidden implementation body or reopen dynamic-compatibility checking at the call site.

### 58.7 Root host/embedding conformance

Root validation uses a separate judgment conceptually:

```text
RootContract ⊢root ApplicationRoot
```

where `ApplicationRoot` is an already well-typed application/embedding root and `RootContract` is the selected root host/embedding contract from [§48.4](10-host-and-ffi.md#484-root-and-embedding-contracts). The judgment checks exactly the root-integration obligations of [§48.5](10-host-and-ffi.md#485-root-conformance): startup/entry compatibility, provision of host-supplied external service/effect implementations, scheduler/event integration including [§69.6](#696-cooperative-scheduler) runnable-strand progress, any host-driven finite-return assumptions relied on by no-`diverge` contracts, referenced native-adapter trust metadata, and root lifecycle ownership.

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
- a defect reaching `ForeignBarrier` follows the audited defect-rendezvous protocol of [§56.1](10-host-and-ffi.md#561-same-domain-synchronous-callback).

An audited stack-preserving synchronous-callback protocol may replace `suspend = forbidden` with `suspend = permitted` for that specific foreign entry. It must still provide the cancellation/defect rendezvous and lifetime/rooting guarantees required by [§56.1](10-host-and-ffi.md#561-same-domain-synchronous-callback). In 0.0.4, such a protocol does not change `algebraic-crossing = forbidden`.

## 59. Function introduction and application

### 59.1 Introduction

Schematic closure typing:

```text
TypingEnvironment, parameters ; Regions ; Handlers ; Taskgroups ; BodyUsage ; BodyAccess ; BodyControl ⊢ body : BodyResultType ! BodyEffects ▷ BodyCaptures
EnvironmentCaptures = tracked outer obligations retained by body
BodyResultCaptureBound = finite union of whole parameter/environment sources and atoms covering BodyCaptures under §13.4
-----------------------------------------------------------------
TypingEnvironment ; Regions ; Handlers ; Taskgroups ; Usage ; Access ; Control ⊢ fn(parameters){body} :
    fn(ParameterTypes...) ->{BodyEffects} BodyResultType captures EnvironmentCaptures [result-captures <= BodyResultCaptureBound] ! {} ▷ EnvironmentCaptures
```

Constructing the closure is pure unless evaluating expressions used to construct an explicit captured object itself performs effects.

`BodyAccess` introduces caller-supplied grants for access-mode parameters. A `mut` parameter is checked under that supplied authority, not as a newly owned root; updates through it follow [§14.3](04-captures-and-access.md#143-mut) without requiring its type to satisfy `MutableOwner` or name the parent region. Root-grant charges introduced by the body and explicitly declared effects of its calls participate in ordinary effect composition and permitted handler/region elimination to produce the residual `BodyEffects`. Supplied grants and their authority cannot enter `EnvironmentCaptures` or escape in the result. Ordinary values legally copied through them retain their own provenance, which participates in `BodyCaptures` and the result-capture bound ([§13.4](04-captures-and-access.md#134-conservative-result-capture-bounds)).

The callable usage predicates are derived from `EnvironmentCaptures`. `BodyResultCaptureBound` is semantic callable metadata and may be omitted from ordinary source rendering while remaining part of the full type/interface contract. Sources are widened to whole arguments/environments before publication; local component precision is not part of this contract.

### 59.2 Application consumes one callable instance

For a callable contract conceptually containing:

```text
callable : fn(ParameterModesAndTypes...) ->{CallableEffects} CallResultType captures EnvironmentCaptures
result-captures <= CallableResultCaptureBound
```

application consumes one logical instance of `callable` under the usage environment.

If the binding/value is `Dup`, the checker may semantically duplicate it so the source binding remains usable. If it is affine/linear, the call counts as its consuming use.

Arguments are evaluated left-to-right before establishing call-scoped access grants. The result capture summary is computed from the semantic contract:

```text
ResultCaptures = {}                                      if CallResultType is provably capture-free
              = captures required by CallResultType
                union substituted CallableResultCaptureBound   otherwise
```

Substitution replaces each whole argument/environment source by its capture summary. For an access-mode parameter, this is the summary of the accessed value, not of the grant or its authority ([§13.4](04-captures-and-access.md#134-conservative-result-capture-bounds)). Each surviving `mut` owner also receives the conservative post-call union of [§13.6](04-captures-and-access.md#136-canonical-interfaces-and-conservative-mutation), independently of the returned value's bound.

If `mayAbandon(Control, CallableEffects)` holds under [§17.3](05-effects-and-failure.md#173-derived-continuation-control-envelope), application also checks the relevant enclosing continuation segment(s) in `Control` using the ordinary non-local-exit judgment. For an unconstrained open effect-row variable this check uses the conservative abandoning envelope. Thus an opaque effectful call cannot silently acquire the ability to abandon live non-`Discard` caller obligations.

If `Control` contains an ordinary synchronous foreign-control barrier, application additionally enforces [§58.8](#588-foreign-control-barriers): a callable whose admitted row contains `suspend` cannot be invoked there, and every residual algebraic family that may be performed by the call must resolve to a handler on the callback side of the barrier. This barrier check is distinct from `mayAbandon` and `NonAbandoning`.

Application at an opaque boundary also enforces [§45.1](09-concurrency.md#451-group-baseline)'s inheritance rule whenever the admitted row may contain `suspend`: residual algebraic operations may belong to nested children, so their ambient handlers must be duplicable and result-preserving. This check is independent of whether the current call actually suspends or spawns on a particular execution.

### 59.3 Access modes

For a plain argument or an unprefixed `value.method(...)` receiver, ownership/value semantics apply.

For an explicit `view` argument or `view value.method(...)` receiver, the checker creates a shared non-consuming dynamic-call grant.

For an explicit `mut` argument or `mut value.method(...)` receiver, the checker accepts either (1) a root value satisfying `MutableOwner<T,@r>` for an in-scope region/state schema, or (2) a projected mutable grant already derived from a valid parent owner. It then creates/propagates the exclusive dynamic-call grant and rejects conflicting active access to the same root owner/projection identity.

Forwarding a callee's supplied `mut` parameter likewise propagates its existing grant; it does not require a new `MutableOwner` judgment for the parameter type. Each root grant formed from an owned value contributes its region state to `RootGrantEffects`; forwarding or projection contributes no additional entry solely for granting access. The complete call-expression effects are:

```text
RootGrantEffects requires state<@r> for each region of a root grant formed at this call
CallEffects = commonAmbient(CallableEvaluationEffects, ArgumentEvaluationEffects,
                            CallableEffects, RootGrantEffects)
```

`commonAmbient` denotes the checking/weakening rules of [§16.5](05-effects-and-failure.md#165-scoped-row-equality-inference-and-weakening), not a source row-union operator. Root grants in the same region reuse one ambient state slot, including an already-admitted slot for that region. `CallableEffects` is the invoked callable's declared row, including any explicitly admitted state entries, and MUST NOT be reduced using access authority. Updates through supplied grants use `Access` authority as specified in [§14.3](04-captures-and-access.md#143-mut). This rule is determined by parameter/receiver modes and preserved grant or mutable-owner provenance, including across dynamic dispatch; imported bodies are not consulted.

For example, forwarding a supplied grant is region-independent:

```eldude
fn invokeMut<T, R, !e, ..C>(
    mut item: T,
    f: fn(mut T) ->{| e} R captures {..C},
) ->{| e} R {
    f(mut item)
}
```

The helper supplies the existing grant and admits `e`. Calling it with `mut owner` where `owner` is an owned root in `@r` admits `{state<@r> | e}`. Any updates the callback performs through `item` use that supplied authority; its other effects remain in `e`.

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

Nominal containers and `any Trait` packages preserve capture/provenance transitively. Type abstraction cannot erase lifetime/resource provenance required for soundness. Function/method application substitutes whole-value sources in the callable's `ResultCaptureBound`; erasure does not reset that summary.

Freely aliasable region storage additionally obeys the fixed retention-horizon rule: a write into `Ref<T,@r>` is rejected when the stored value retains any provenance whose validity can end before `@r`.

### 60.3 Scoped foreign provenance

A safe foreign/runtime API may introduce a fresh non-denotable provenance atom with a lexical/dynamic validity horizon. Temporary marshalling ([§53.4](10-host-and-ffi.md#534-temporary-marshalling)) is the canonical example. Conceptually, for fresh `MarshalProvenance`:

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
TypingEnvironment ; Regions,@r ; Handlers ; Taskgroups ; Usage ; Access ; Control ⊢ body : ResultType ! BodyEffects ▷ Captures
ResidualEffects = BodyEffects with all fixed state<@r> entries discharged
@r not free in ResidualEffects (including its open tail)
@r not free in ResultType
@r not retained by Captures
@r not present in any live child/result provenance in Taskgroups or escaping foreign provenance
all @r ownership obligations discharged
-----------------------------------------------------------------
TypingEnvironment ; Regions ; Handlers ; Taskgroups ; Usage ; Access ; Control ⊢ region r { body } : ResultType ! ResidualEffects ▷ Captures
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

A foreign-control barrier is not a structural discharge owner and does not make an otherwise illegal non-local exit legal. Its additional role is prohibitive: under [§58.8](#588-foreign-control-barriers) it prevents ordinary suspension through, and algebraic continuation capture across, the waiting foreign frame.

### 62.3 Diverging and defect paths

A syntactically diverging path is not treated as if it had consumed arbitrary resources. Runtime responsibility remains governed by cleanup/taskgroup/host contracts. `diverge` records possible nonreturn.

Likewise, a nonrecoverable assertion-defect path is not a completed usage path and is not treated as if it had consumed arbitrary naked resources. Explicit structural owners still perform their specified best-effort defect unwinding; no Eldude continuation may recover a naked obligation after the defect.

### 62.4 Field projection and pattern ownership

For a visible field `field: FieldType` of `AggregateType`, value projection is checked as follows ([§8.1](02-types-and-ownership.md#81-products)):

```text
receiver is an available owned binding or an active access-grant binding to AggregateType
FieldType : Dup
---------------------------------------------------------------
receiver.field : FieldType; receiver ownership/access is preserved
```

A computed owned receiver additionally requires `AggregateType: Discard`; its evaluation effects occur once and its temporary is discarded after projection. The result retains the copied field's capture/provenance summary. Optional field projection applies the same checks to its `Option` receiver ([§21.6](05-effects-and-failure.md#216-optional-access-and-coalescing)).

Owned pattern checking consumes the complete matched value and transfers component obligations recursively to subpatterns ([§8.4](02-types-and-ownership.md#84-pattern-matching)). A name binds the matched owned value; `_` discharges it only when `Discard` holds. Tests and guards inspect before committing those transfers. A pattern checked against an access grant performs no owned transfer or discard: ordinary value bindings require `Dup`, while ignored components remain owned by the caller. No judgment produces a partially moved aggregate or escaping grant.

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

For `while`, the condition is checked at the header on every iteration. Its true edge feeds the body and its false edge is an ordinary loop exit. For `for`, source evaluation/iterator acquisition occurs once before the header. Each successful `next` introduces a fresh item and the returned remainder; the remainder is the protocol's explicitly threaded loop owner, whose type/usage and tracked provenance contract must be preserved on every continuing edge ([§35](08-collections.md#35-iteration)). This internal iterator replacement does not add source assignment or implicit replacement of outer bindings. The iteration pattern obeys [§8.4](02-types-and-ownership.md#84-pattern-matching), including `Discard` for ignored owned items.

After checking back-edges, all condition-false/iterator-completion exits and all `break` exits targeting this loop are joined by [§62.5](#625-usage-environments-and-branch-joins). A possibly zero-iteration loop includes its zero-iteration exit. `break` has no value and does not restore consumed bindings. Early exit with a live iterator remainder remains subject to [§35.3](08-collections.md#353-for). A loop with no normal exit contributes no state to the following continuation; possible `diverge` or defects do not erase obligations on paths that do continue.

Termination/progress checking ([§19](05-effects-and-failure.md#19-non-divergence)) is independent of these ownership checks. A finite-iteration or structural-recursion proof cannot justify an incompatible usage back-edge.

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
- evaluating `e` under the canonical cleanup structural control context `CleanupControl` satisfies `mayAbandon(CleanupControl, e) = false` under [§17.3](05-effects-and-failure.md#173-derived-continuation-control-envelope); equivalently, the cleanup mask may neutralize the cancellation edge of `suspend` but no escaping `affine` family may remain; an affine operation may choose zero resumptions and therefore cannot be part of the residual cleanup contract;
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

For an operation `operation` in fully applied effect family `EffectFamily` returning the substituted `OperationResult` and selected instance `EffectInstance`:

```text
arguments well typed
EffectInstance : EffectFamily selected
------------------------------------------------
!EffectFamily::operation(arguments) : OperationResult ! {EffectFamily@EffectInstance}
```

If the selected operation mode is `affine`, the checker also identifies the captured segment from the operation to the matching handler delimiter and requires that possible zero-resumption abandonment be a legal non-local exit before accepting the operation site. This check depends on the declaration mode, not on inspecting a particular handler body.

If `Control` contains a synchronous foreign-control barrier between the operation site and the otherwise selected handler delimiter, the operation is rejected before the mode-specific continuation rule is applied. This is true for `tail`, `once`, and `affine`: an arbitrary waiting foreign frame is not part of an Eldude delimited continuation merely because the operation is non-abandoning.

An `affine` operation returning `Never` is treated by the same ordinary affine rule when its handler is reachable without crossing a foreign-control barrier; safe code cannot take its resuming path because it cannot supply a `Never` value.

Source interfaces normally display fully applied families rather than elaborated instance identities. Family argument substitution is fixed at instance creation ([§17.4](05-effects-and-failure.md#174-effect-instances)); rows, forwarding, and handler elimination preserve those arguments. Lexically fixed instance identities remain tracked wherever they affect dispatch or escape safety.

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
- result-capture bound for the `handle` expression.

If the handled body has:

```text
HandlerInputType ! {EffectFamily@EffectInstance | HandlerBodyEffects}
```

then the handled result has type/effect approximately:

```text
HandlerOutputType ! ResidualEffects
ResidualEffects = commonAmbient(HandlerBodyEffects, ClauseResidualEffects, ReturnClauseEffects)
```

The selected slot is removed exactly once by splitting it from the handled body row; `HandlerBodyEffects` is already the remainder. No further matching family entries are deleted from that remainder. `ClauseResidualEffects` contains the clauses' outward effects after interpreting explicit `self` dispatch through the current frame ([§26.4](06-handlers.md#264-same-family-operations-inside-clauses)), including outer-instance slots required by forwarding or explicit outer dispatch. `commonAmbient` follows [§16.5](05-effects-and-failure.md#165-scoped-row-equality-inference-and-weakening) and preserves those slot identities. A body that does not use the installed handler may first weaken to admit its unused slot.

Intrinsic `diverge`, `suspend`, and region state effects are not removed merely because an algebraic family is handled.

Installing the lexical handler transfers `HandlerCaptures` into one linear handler-frame usage state. The `handle` expression's output capture summary is computed from `HandlerCaptures`, the handled computation's result captures, and clause-produced values. Deep clause re-entry references this same logical frame state; it does not duplicate it.

At explicit or implicit resumption, the static usage transition splits the frame environment by `Dup`: every non-`Dup` frame binding is consumed from the clause-side usage environment and transferred into the resumed computation, while `Dup` bindings may remain available on both sides by ordinary semantic duplication. If the resumption returns, its `HandlerOutput` returns to the clause but transferred non-`Dup` frame bindings do not. The resumed computation is responsible for the ordinary usage/discharge of those transferred obligations. Zero-resumption affine paths retain their frame state locally and must satisfy terminal discharge themselves.

### 64.3 Resumption capability

Inside a resumable clause, the checker introduces an internal non-denotable capability conceptually:

```text
Resume<mode, OperationResult, HandlerOutput, FrameUsage>
```

`FrameUsage` is compiler bookkeeping for the ordinary usage state transferred by [§23.3](06-handlers.md#233-active-handler-frame-obligations)/[§64.2](#642-lexical-handler-application); it is not a source-level ownership mode or denotable type parameter. A `tail` clause body is checked as `OperationResult`; after its local result boundary has discharged, the compiler inserts the capability's one tail resumption. For `once` and `affine`, source code accesses the capability through `resume(value)` and the clause produces `HandlerOutput` under its mode's rules.

The capability cannot escape the clause.

The non-normative [`tools/handlers.py`](../../tools/handlers.py) experiment checks a restricted annotated expression fragment for these rules and lowers it to explicit handler evidence for execution in a small interpreter. Its [cases](../../tools/test_handlers.py) cover implicit tail resumption after local cleanup, ownership transfer across deep once resumption, affine segment discharge, and forwarding to outer instances. The [repository README](../../README.md#handler-and-resumption-experiment) records its conservative restrictions and runtime limits; the experiment is not a complete implementation of these judgments.

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

The same abandonment model is invoked indirectly at an ordinary call when the call's derived continuation-control envelope is potentially abandoning. Many-shot continuation duplication is not part of the 0.0.4 core.

## 66. Error typing

### 66.1 `?`

If:

```text
expression : Result<ErrorType, SuccessType>
```

then `expression?` has local success type `SuccessType` and an error-propagation edge carrying the same nominal `ErrorType` to the nearest `try` or enclosing function result. Within a `tail` clause, the local result delimiter of [§25.2](06-handlers.md#252-tail) replaces the enclosing function boundary: propagation may target a `try` inside the clause or its operation result, never an outer `try` or function.

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
- for each child effect that would resolve through a handler in the taskgroup baseline, requires both frame `Dup` and the result-preserving inheritance check of [§45.1](09-concurrency.md#451-group-baseline); inherited delimiters preserve `ChildResultType` and `ChildCaptures`;
- produces `Task<ChildResultType>` carrying group provenance `TaskgroupId` together with the child result provenance `ChildCaptures` that a later `await` may reveal;
- does not itself perform `ChildEffects` in the parent strand;
- does not itself add `suspend` merely by child creation.

The enclosing `taskgroup` expression includes child effects, including inherited handler residuals, and admits `suspend` when it may own any child. A handler explicitly installed in `childExpression` is checked before deriving `ChildResultType` and may change that type under the ordinary handler rule.

### 67.3 Task provenance non-escape

A result/capture leaving the group may not retain `TaskgroupId`.

This rule rejects escaping task handles transitively through containers, closures, regions, or `any` packages.

### 67.4 Await

`await task` for `task: Task<TaskResultType>` consumes the handle, adds `suspend`, returns `TaskResultType` with the child result-capture/provenance summary carried by the handle, and adds a control-dependency edge to that child's completion. This result summary includes any widening required by [§13.6](04-captures-and-access.md#136-canonical-interfaces-and-conservative-mutation) when the task crossed an abstraction boundary; awaiting cannot remove those conservative dependencies. A provably capture-free `TaskResultType` has an empty result summary.

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

Deep resumption reinstalls the same handler around the continuation. A `tail` clause first evaluates to its operation result under the local result delimiter of [§25.2](06-handlers.md#252-tail) and completes clause-local discharge, then performs this resumption implicitly.

### 69.6 Cooperative scheduler

A runnable strand executes until an actual suspension point or termination. The scheduler selects another runnable strand only then.

Scheduling itself is not an admitted source of nontermination. When the current strand suspends/terminates and at least one Eldude strand in the same execution domain is runnable, the abstract machine MUST take a scheduler transition selecting some runnable strand rather than stuttering indefinitely in scheduler state. The implementation may choose any runnable strand.

This is a minimal runnable-strand progress property, not a fairness, priority, latency, or bounded-response guarantee. Eldude does not promise that every continuously runnable strand receives service within a time bound or before another runnable strand. Delays caused by external events, host services, foreign completion, locks/protocols outside the language model, or other non-runnable dependencies remain governed by their declared finite-return contracts and admit `diverge` when termination is not justified.

The root host/runtime contract MUST implement scheduler/event integration consistently with this rule. A host cannot preserve a no-`diverge` Eldude contract while introducing unmodelled indefinite starvation of runnable Eldude work.

### 69.7 Cancellation

A cancellation request marks the target strand/group state. Delivery occurs when execution reaches an ordinary suspension point unless cancellation is currently structurally protected by cleanup or taskgroup shutdown. Static typing guarantees that every such unmasked suspension point is a legal cancellation structural exit.

### 69.8 Defect unwinding

Assertion defect initiates best-effort structural unwinding rather than a recoverable control effect. Cleanup/taskgroup obligations execute according to their rules and the primary/secondary defect precedence of [§20.2](05-effects-and-failure.md#202-defect-semantics) before the defect reaches the host boundary, unless progress is prevented by divergence or process-level termination. Naked linear obligations are not required to have an Eldude-level discharge path because no Eldude continuation survives the defect.

### 69.9 Foreign callback boundaries

Entering an ordinary same-domain synchronous callback pushes the internal foreign-control barrier of [§58.8](#588-foreign-control-barriers). The callback executes as nested Eldude execution on the same domain and returns to the waiting native frame only by ordinary callback return or by the audited private defect-rendezvous path.

Under the ordinary barrier, execution cannot take an Eldude suspension transition. A pending cancellation request is therefore retained in machine state until control returns through the foreign call and a later ordinary unmasked suspension point is reached. Algebraic operation dispatch cannot select a handler outside the barrier.

Every callback-entry transition first checks the enclosing synchronous invocation chain for a pending defect. If one exists, the shim takes only the private suppression transition of [§56.1](10-host-and-ffi.md#561-same-domain-synchronous-callback); it does not enter Eldude.

At the first defect-processing transition, the runtime records the defect and marks every active enclosing synchronous invocation pending before any callback-local discharge or native call. Callback-local structural unwinding then proceeds while possible; the barrier returns through the native frame using the audited rendezvous protocol, and outer Eldude defect unwinding resumes only when the corresponding Eldude boundary is regained. Removing an inner rendezvoused frame does not clear enclosing pending states. Native non-local unwinding across live Eldude frames is not part of ordinary safe-machine execution.

An audited stack-preserving callback protocol may permit suspension by preserving the waiting native execution state and all required roots/lifetimes. Resumption must re-enter the same logical callback computation according to that protocol. Such an implementation remains subject to ordinary Eldude cancellation semantics at the permitted suspension point and still does not permit algebraic handler lookup across the foreign-control barrier in 0.0.4.

## 70. Soundness obligations

A conforming safe implementation must uphold at least the following properties.

### 70.1 Type preservation

A well-typed reduction preserves type correctness and the admitted semantic contract of the expression.

### 70.2 Progress

A closed well-typed expression is a value, can take a semantic step, is suspended on an admitted operation/wait, is undergoing specified structural shutdown, or has reached an explicit defect/host boundary. It does not become stuck because a safe-language invariant was omitted.

### 70.3 Effect safety

A computation cannot perform an unadmitted ordinary effect, modulo the semantics of handler interpretation and canonical effect weakening. Updates through a supplied `mut` grant are admitted by its explicit access contract and state authority ([§14.3](04-captures-and-access.md#143-mut)); the root invocation MUST account for that authority's region state. This does not admit independent state effects or permit removing an explicitly declared effect from a call's row.

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

No safe spawned child outlives its owning taskgroup, and no task handle escapes its group provenance. Inherited handlers preserve each child's result type and provenance under [§45.1](09-concurrency.md#451-group-baseline); frame duplicability alone is insufficient.

### 70.10 Cleanup safety

Discard alone performs no cleanup effect. `using` initiates canonical cleanup for still-live owned resources on every specified structural exit, with cancellation protection. No residual algebraic effect capable of abandoning the cleanup continuation may escape a `Cleanup` invocation, and cleanup defects follow the general structural-discharge precedence rules of [§20.2](05-effects-and-failure.md#202-defect-semantics).

### 70.11 Trait coherence

For the admitted fragment of [§§10.6](03-traits.md#106-implicit-implementation-patterns-and-selection)–[10.8](03-traits.md#108-associated-equations-and-normalization), implicit trait resolution and associated/GAT normalization are unique, terminating, and independent of import order. Matching, overlap, prerequisite decrease, and opaque-projection equality are defined language rules, not implementation-selected acceptance criteria.

### 70.12 Non-divergence

When `diverge` is absent, the compiler/runtime contracts justify absence of admitted nontermination under all relevant primitive, handler, host, task-dependency, scheduler-progress, and foreign assumptions. The scheduler-progress premise is the minimal no-stuttering rule of [§69.6](#696-cooperative-scheduler); it is not a general fairness theorem. Normal return is not guaranteed in the presence of an explicit assertion defect or externally delivered structural cancellation; those remain separate nonrecoverable/structural outcomes rather than `diverge`.

### 70.13 Foreign-boundary control safety

An ordinary safe same-domain synchronous callback cannot suspend through an arbitrary waiting foreign frame and cannot capture/resume an Eldude algebraic continuation whose matching handler lies outside that foreign-control barrier. Eldude defects do not unwind arbitrarily through foreign frames, and arbitrary foreign threads do not directly execute unrestricted Eldude code. Any stronger stack-preserving, thread-attachment, or cross-language unwind behavior is confined to an explicitly audited host/native trust boundary and does not silently weaken these portable guarantees.

---

[Specification index](../language-specification.md) · Previous: [10. Host, unsafe code, and FFI](10-host-and-ffi.md) · Next: [12. Interfaces, compilation, and tooling](12-interfaces-and-tooling.md)
