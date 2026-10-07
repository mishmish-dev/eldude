# Chapter 6 — Handlers and resumption

[Specification index](../language-specification.md) · Previous: [5. Effects, termination, and failure](05-effects-and-failure.md) · Next: [7. Regions, mutable state, and cleanup](07-state-and-cleanup.md)

This chapter explains lexical effect interpretation, resumption, forwarding, and the ownership obligations carried through each operation.

**Prerequisites:** [4. Closures, captures, and scoped access](04-captures-and-access.md), [5. Effects, termination, and failure](05-effects-and-failure.md).

The numbered rules are normative under the [specification conventions](../language-specification.md). Examples are illustrative snippets; names and omitted bodies may stand for surrounding program or library context.

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
        print(text) => terminalWrite(text);

        readLine() => {
            resume(terminalRead());
        }
    }
}
```

The handler is lexical and not a first-class `Handler` value. A reusable interpreter can be expressed by an ordinary wrapper function that installs the same lexical handler around a supplied computation.

## In this chapter

- [23. Lexical handler frames](#23-lexical-handler-frames)
- [24. Handler application and instances](#24-handler-application-and-instances)
- [25. Handler clauses and resumption](#25-handler-clauses-and-resumption)
- [26. Handler completion, forwarding, and residual rows](#26-handler-completion-forwarding-and-residual-rows)

## 23. Lexical handler frames

### 23.1 Handlers are not first-class values

Eldude has no public `Handler<...>` value type. A handler is a lexical interpreter block written only as part of a `handle` application:

```eldude
handle {
    greet()
} with handler Console {
    print(text) => terminalWrite(text);

    readLine() => {
        resume(terminalRead());
    }
}
```

The compiler infers the handled family, output type, residual effect row, retained captures/provenance, and result-capture bound of the whole `handle` expression.

Reusable interpretation is expressed by an ordinary wrapper function that installs the lexical handler around a supplied computation. This reuses ordinary function types, captures, effects, and separate-compilation contracts instead of introducing a second first-class callable package.

Conceptually:

```eldude
fn withTerminal<A, !e, ..C>(
    body: fn() ->{Console | e} A captures {..C},
) ->{io | e} A
{
    handle {
        body()
    } with handler Console {
        print(text) => terminalWrite(text);

        readLine() => {
            resume(terminalRead())
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

At a resumption boundary, including the implicit resumption of a `tail` clause, handler-frame ownership is threaded as follows:

- every non-`Dup` frame capture is **moved into the resumed computation**;
- those moved captures are unavailable to code in the resuming clause after `resume(...)` returns;
- a `Dup` frame capture may be semantically duplicated, allowing one copy to remain available to the clause while one is available to the resumed computation;
- the resumed computation, including re-entered clauses and any `return` clause reached while it runs, owns the moved frame state and must obey ordinary usage rules for it.

Therefore a `tail` clause's implicit final resumption transfers all non-`Dup` frame captures after clause-local discharge. A `once` clause, or the resuming path of an `affine` clause, may continue after `resume`, but that post-resume continuation is checked with the moved non-`Dup` captures absent from its usage environment. It may continue using only captures that remained legally available (for example `Dup` captures) plus values produced independently by the resumed computation.

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

Handlers are deep. Explicit or implicit resumption reinstalls the same handler around the resumed computation, using the handler-frame usage state transferred by [§23.3](#233-active-handler-frame-obligations). Re-entry therefore shares the same logical frame ownership state rather than manufacturing a fresh copy of retained obligations.

Shallow handlers are not part of the current design.

## 25. Handler clauses and resumption

### 25.1 Lexical resumption

Each resumable clause has exactly one internal lexical resumption capability. It has no user-denotable variable. A `tail` clause uses it implicitly on normal completion; `once` and `affine` clauses use it explicitly:

```eldude
readLine() => {
    resume(terminalRead());
}
```

`resume(value)` is the only explicit source syntax for resuming and is available only when the innermost enclosing operation clause is `once` or `affine`. Writing an explicit `resume` for a `tail` clause is a semantic error; nested handlers introduce their own capabilities normally.

The resumption cannot be stored, returned, passed, captured by a nested closure, or otherwise escape the clause.

### 25.2 `tail`

A `tail` clause is checked against its declared **operation result type**, not the whole handler's output type. Its expression result, or an explicit clause-local `return`, supplies that operation result. The compiler then resumes exactly once as the clause's final semantic action:

```eldude
effect Read { tail value() -> Int; }

handle { !Read::value() + 2 } with handler Read {
    value() => 40;
}
```

Conceptually the clause elaborates to evaluation under a local result delimiter, followed by an internal `resume(result)`. This delimiter is not a first-class closure, does not copy the handler frame, and grants no extra capture or access permissions.

Every normally completing path, including a clause-local early `return`, MUST produce the operation result. Before implicit resumption, all clause-local scopes crossed by that result exit finish their ordinary discharge: `using` cleanup runs, taskgroups resolve, and regions satisfy non-escape. Handler-frame captures remain governed by [§23.3](#233-active-handler-frame-obligations) and transfer at the subsequent resumption; they are not clause-local leftovers to discard. No clause-local cleanup may remain scheduled after the resumed computation returns.

`return` targets this local result delimiter unless it occurs in a nested function. `?` targets the nearest lexical `try` within that delimiter, with the exact error-type check of [§21.3](05-effects-and-failure.md#213-postfix-); it cannot skip an incompatible inner `try`. If no such `try` exists, the declared operation result must be the corresponding `Result<E,T>`, and `Err(error)` becomes the value supplied to implicit resumption. Neither form escapes to a function or `try` outside the clause. A `break` or `continue` cannot target an outer loop across the delimiter.

If clause evaluation or its discharge diverges, defects, or exits through legal outward algebraic control/cancellation, no implicit resumption is reached. Those outcomes retain their ordinary residual effects and structural-exit checks, including discharge of any suspended continuation obligations crossed by an outward exit. Automatic resumption grants no new permission to abandon that continuation. The exactly-once condition concerns normal completion, as for an ordinary function-like operation. An operation returning `Never` has no normally completing `tail` implementation.

Implementations SHOULD lower eligible tail operations without allocating a general continuation.

### 25.3 `once`

A `once` clause MUST resume exactly once. The clause may continue after the resumed computation returns, but its post-resume usage environment does not contain any non-`Dup` handler-frame captures moved into the resumption under [§23.3](#233-active-handler-frame-obligations).

### 25.4 `affine`

An `affine` clause may resume zero or one time.

If it does not resume, abandoning the captured continuation segment must be a legal non-local control exit under ordinary usage, cleanup, region, taskgroup, and capture rules.

### 25.5 Abortive affine operations

Eldude has no separate abort resumption mode. An `affine` operation returning `Never` is semantically abortive in safe code because no `Never` value can be supplied to `resume`.

Such an operation still uses the ordinary affine operation-site and zero-resumption abandonment rules; no additional continuation mode is introduced.

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
        terminalWrite(text);
        ()
    }

    forward readLine;
}
```

`forward ..;` forwards every otherwise omitted operation.

### 26.3 Forwarding

Forwarded operations target the next outer instance of the same fully applied family. They do not erase, change, or re-infer its generic arguments. Forwarding contributes that outer slot to the residual ambient row, even when its printed label equals the intercepted label. If no outer instance is installed locally, the application remains an outward requirement in the resulting effect row.

### 26.4 Same-family operations inside clauses

Inside a clause, an unqualified operation of the handled family is an error.

Explicit recursion to the current instance uses:

```eldude
!self::op(...)
```

Explicit outer-instance dispatch uses the named outer instance.

Dispatch through `self` is interpreted by the current frame and does not add an outward slot for that frame. Any effects introduced by the recursively entered clauses remain in the handler residual, and ordinary termination and frame-usage checks still apply. This prevents accidental self-recursion or forwarding.

### 26.5 Residual row

Every `handle` expression has a complete residual effect row, including:

- effects introduced by operation clauses;
- effects introduced by the return clause;
- intrinsic semantic effects introduced by handler implementation;
- outer slots of the handled family required by forwarding or explicit outer-instance calls.

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

## B.11 Forwarding

```eldude
fn runPrintOnly(body: fn() ->{Console} Unit) ->{log, Console} Unit {
    handle {
        body()
    } with handler Console {
        print(text) => writeLog(text);

        forward readLine;
    }
}
```

The wrapper's residual row contains both the logging effect and `Console` because `readLine` may be forwarded.

---

[Specification index](../language-specification.md) · Previous: [5. Effects, termination, and failure](05-effects-and-failure.md) · Next: [7. Regions, mutable state, and cleanup](07-state-and-cleanup.md)
