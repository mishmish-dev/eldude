# Chapter 9 — Structured concurrency

[Specification index](../language-specification.md) · Previous: [8. Collections and iteration](08-collections.md) · Next: [10. Host, unsafe code, and FFI](10-host-and-ffi.md)

This chapter defines cooperative scheduling, taskgroup ownership, cancellation, and the interaction between children and handlers.

**Prerequisites:** [5. Effects, termination, and failure](05-effects-and-failure.md), [6. Handlers and resumption](06-handlers.md), [7. Regions, mutable state, and cleanup](07-state-and-cleanup.md).

The numbered rules are normative under the [specification conventions](../language-specification.md). Examples are illustrative snippets; names and omitted bodies may stand for surrounding program or library context.

## B.15 Structured concurrency

```eldude
enum FetchBothError {
    User(UserError),
    Orders(OrderError),
}

fn fetchBoth(id: UserId)
    ->{net, suspend, diverge}
      Result<Pair, FetchBothError>
{
    taskgroup {
        let userTask = spawn fetchUser(id);
        let orderTask = spawn fetchOrders(id);

        Result::Ok(Pair {
            user: (await userTask).mapError(FetchBothError::User)?,
            orders: (await orderTask).mapError(FetchBothError::Orders)?,
        })
    }
}
```

Both spawned result types must be `Discard`. The parent explicitly maps distinct child error types into one nominal error type before `?` propagation.

## In this chapter

- [38. Execution domains and strands](#38-execution-domains-and-strands)
- [39. `taskgroup`](#39-taskgroup)
- [40. `spawn`](#40-spawn)
- [41. `Task<T>`](#41-taskt)
- [42. `await`](#42-await)
- [43. Cancellation](#43-cancellation)
- [44. Effects of concurrent children](#44-effects-of-concurrent-children)
- [45. Handler environment of children](#45-handler-environment-of-children)
- [46. Structured racing](#46-structured-racing)
- [47. No detached tasks or general supervisor primitive in the core](#47-no-detached-tasks-or-general-supervisor-primitive-in-the-core)

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

The current language does not specify a general source-level shared-memory parallelism API or memory model. User-directed multicore execution of ordinary Eldude strands is outside the language scope; programs requiring it must currently use host/native facilities.

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

If the body attempts a continuing structural exit of [§62.2](11-formal-semantics.md#622-non-local-exit-judgment) across the group, or reaches a nonrecoverable defect, the taskgroup:

1. records the current structural outcome;
2. requests cancellation of all outstanding children;
3. drains children until they terminate, subject to possible `diverge`;
4. allows child `using` cleanup to run under its cancellation-protected rules;
5. propagates the resulting primary outcome after structural shutdown completes.

If a first defect is observed during shutdown while a non-defect outcome was pending, the defect becomes primary and the previous outcome becomes suppressed diagnostic context. If a defect was already primary, later child/cleanup defects are secondary diagnostics. This is the general precedence rule of [§20.2](05-effects-and-failure.md#202-defect-semantics).

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
let x = (await task)?;
```

may choose to propagate that error, after which normal taskgroup early-exit shutdown applies.

### 39.6 Child defects

If a child assertion-defects, the group enters structural defective shutdown: siblings are cancellation-requested and drained and cleanup runs. The child defect becomes the primary outcome unless an earlier defect is already primary, in which case it is secondary diagnostic information.

The defect is not converted into `Result` or a task outcome value. A child defect observed while a return, `?`, affine zero-resumption outcome, or cancellation was pending supersedes that non-defect outcome according to [§20.2](05-effects-and-failure.md#202-defect-semantics).

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

and prevents hiding the handle in a closure, `any` package, or container that outlives the group. A task handle is not `CaptureFree` and cannot be a `Ref` payload at all, regardless of the cell's region lifetime ([§13.5](04-captures-and-access.md#135-retention-horizons)).

### 41.3 Discarding a handle

Discarding `Task<T>` has no semantic effect.

The child continues to exist under the taskgroup's ownership. At normal group exit it is awaited/drained; at abnormal group exit it is cancellation-requested and drained.

Discarding a handle is therefore structured fire-and-forget, not detachment.

## B.16 Discarded task handle

```eldude
taskgroup {
    spawn refreshCache();
    serveRequest()
}
```

Discarding the handle does not cancel the child. The taskgroup still waits for it at normal exit or cancels/drains it on abnormal exit.

## 42. `await`

### 42.1 Result

```eldude
await task
```

consumes `Task<T>` and returns exactly `T`.

There is no mandatory `TaskOutcome<T>` wrapper.

A child `Result::Err` remains the ordinary `T` value when `T = Result<A,E>`.

### 42.2 Suspension

`await` admits `suspend` because the current strand may need to yield until the child completes.

If the child is already complete, the particular execution need not actually suspend.

### 42.3 Termination dependency

Awaiting a known non-diverging child does not inherently require `diverge`.

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

Every reachable ordinary suspension point MUST be statically legal as a cancellation exit under [§62.2](11-formal-semantics.md#622-non-local-exit-judgment). A naked live linear obligation with no valid discharge path across that point therefore makes the program ill-typed; cancellation is not silently disabled because such an obligation happens to be live.

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

provides an explicit cooperative suspension point for compute-bound code that requires responsiveness. Pending cancellation may be delivered there under the ordinary rule in [§43.2](#432-delivery).

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

## 44. Effects of concurrent children

### 44.1 Lexical child-effect ownership

A child computation's effects are accounted for by the enclosing lexical `taskgroup`.

They are not stored as a type parameter on `Task<T>`.

If:

```eldude
fetch: fn() ->{net, suspend, diverge} Result<Data, E>
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

A child effect may resolve through a baseline handler only when its active frame is `Dup` **and** its clauses satisfy the result-preserving inheritance check below. Each child receives its own frame installation for the same lexical effect-instance identity, with values duplicated only by ordinary `Dup`. The inherited delimiter surrounds that child's computation; it does not capture a parent continuation or run the parent's return clause against a differently typed value.

The inheritance check rechecks the lexical handler with a fresh rigid result type `A`, with no `Dup`, `Discard`, trait, or representation assumptions about `A`, while keeping the handled family application and ordinary environment contracts fixed. The default or explicit return clause must transfer its `A` input unchanged to its result. An operation clause must resume exactly once on each normally completed path and transfer the resulting `A` unchanged to its result. For a `tail` clause this check applies to the elaborated clause including its implicit resumption, not to the source operation result; its automatic resumption forwards `A` unchanged after clause-local discharge. Simple aliases and ownership-preserving transfer through control-flow joins preserve this result identity; inspecting, replacing, packaging, discarding, or passing it to arbitrary code does not. Code before/after resumption may perform its admitted effects and use other values. A `once` clause can therefore log after resumption and return the saved result. All usual resource, cancellation, defect, and non-divergence checks still apply; a defect or admitted divergence does not manufacture an `A` result.

An `affine` declaration is not automatically disqualified if its actual clause passes this exactly-once check, but a normally returning zero-resumption clause cannot pass. Forwarded operations retain their applied family and must resolve only through similarly admissible inherited frames. The operation's declared mode still controls operation-site abandonment checking; inheritance does not strengthen an `affine` operation to `once` in public effect contracts. The inferred residual row and capture contract of the inherited handler must be independent of `A`. These checks are properties of the existing lexical handler source, not a new author-written handler type or permission.

If either frame duplication or this check fails, child dispatch through that frame is rejected unless a suitable handler is installed explicitly inside the child. In particular, a parent handler with `return n => n + 1` cannot be inherited by a `Bool` child merely because its captures are duplicable. A handler installed inside a child may transform the child's result or use affine abandonment under the ordinary rules; the resulting handled expression determines `Task<T>`'s `T`.

An unconstrained open child row is checked against every baseline frame it could select. Shared mutable handler state uses explicit aliasable state such as `Ref`. Each inherited operation/return clause executes as child work and its residual effects belong to the taskgroup; its identity return preserves the child's result type, usage, and provenance. Parent completion separately uses the parent's frame and return clause.

At an opaque ordinary call whose admitted row may contain `suspend`, every residual algebraic application that the call may perform is conservatively treated as potentially performed by a nested child. Its selected ambient frame must therefore satisfy this same duplication/inheritance check. A row variable is checked against every compatible ambient family unless its bounds rule out suspension or that family. This uses the existing row contract: any computation that may spawn a child necessarily admits `suspend` ([§44.3](#443-group-suspension)). It does not inspect imported bodies or introduce a hidden spawning permission. The conservative rule may reject an opaque implementation that actually performs all effects on its parent strand; installing an appropriate handler inside the supplied computation or exposing a non-suspending contract avoids that ambiguity. Direct local operations and visible lexical `spawn` forms use their exact contexts. Root-supplied service interpretations used by children must satisfy the same result-preserving contract at root conformance.

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

This rule prevents `spawn` from becoming an implicit arbitrary dynamic-context capture operation, ensures inherited frame lifetimes enclose their children, and preserves the child's result contract as well as ordinary `Dup` ownership. The authoritative eligibility and delimiter rule is [§45.1](#451-group-baseline).

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

Every race branch and its structured taskgroup/suspension behavior is checked against one common ambient row ([§16.5](05-effects-and-failure.md#165-scoped-row-equality-inference-and-weakening)). Repeated requirements for the same selected slot are shared; distinct handler layers remain distinct.

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
pub fn join2<A, B, !e, ..Ca, ..Cb>(
    left: fn() ->{suspend | e} A captures {..Ca},
    right: fn() ->{suspend | e} B captures {..Cb},
) ->{suspend | e} (A, B)
where A: Discard,
      B: Discard;

pub enum Timeout<T> {
    pub Completed(T),
    pub TimedOut,
}

pub fn timeout<T, !e, ..C>(
    duration: Duration,
    work: fn() ->{clock, suspend | e} T captures {..C},
) ->{clock, suspend | e} Timeout<T>
where T: Discard;
```

Each supplied computation may weaken to the shared ambient row under [§16.5](05-effects-and-failure.md#165-scoped-row-equality-inference-and-weakening); the callbacks need not start with equal closed rows. A bounded concurrent-map combinator may consume arbitrary input elements into children, but every spawned branch result must still satisfy `Discard`; if one callback value is reused across multiple branches, its retained environment must satisfy ordinary `Dup`/`Discard` multiplicity requirements. All such combinators inherit taskgroup effect accounting, cancellation, handler-inheritance, provenance, defect, and drain rules unchanged.

These library operations do not create detached tasks, a public `select` primitive, or a first-class taskgroup lifetime capability.

## 47. No detached tasks or general supervisor primitive in the core

The core language has no operation that detaches a child from its lexical taskgroup.

Long-lived services are structured by an appropriately long-lived outer taskgroup or by host/runtime-owned root scopes whose lifetime is part of the host contract.

A reusable general supervisor API may be designed later, but it must preserve the same ownership/capture principles and cannot extend region-local state past its valid lifetime.

---

[Specification index](../language-specification.md) · Previous: [8. Collections and iteration](08-collections.md) · Next: [10. Host, unsafe code, and FFI](10-host-and-ffi.md)
