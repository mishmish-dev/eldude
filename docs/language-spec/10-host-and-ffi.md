# Chapter 10 — Host, unsafe code, and FFI

[Specification index](../language-specification.md) · Previous: [9. Structured concurrency](09-concurrency.md) · Next: [11. Formal static and dynamic semantics](11-formal-semantics.md)

This chapter describes application runtime integration and the audited contracts required to cross into native code.

**Prerequisites:** [4. Closures, captures, and scoped access](04-captures-and-access.md), [5. Effects, termination, and failure](05-effects-and-failure.md), [7. Regions, mutable state, and cleanup](07-state-and-cleanup.md), [9. Structured concurrency](09-concurrency.md).

The numbered rules are normative under the [specification conventions](../language-specification.md). Examples are illustrative snippets; names and omitted bodies may stand for surrounding program or library context.

## B.19 Opaque foreign callback identity

Conceptually:

```eldude
using (registration = ffi::registerCallback(state, callback)?) {
    run();
}
```

A bundled runtime wrapper may internally use an opaque rooting handle such as `ffi::Handle<State>`. `State` itself remains movable; the exact wrapper type is not a core-language requirement.

## In this chapter

- [48. Host model](#48-host-model)
- [49. Unsafe code](#49-unsafe-code)
- [50. Raw pointers](#50-raw-pointers)
- [51. No pinning or immovable ordinary values](#51-no-pinning-or-immovable-ordinary-values)
- [52. Foreign declarations](#52-foreign-declarations)
- [53. Foreign storage and identity](#53-foreign-storage-and-identity)
- [54. Strings and buffers at the FFI boundary](#54-strings-and-buffers-at-the-ffi-boundary)
- [55. Foreign calls, blocking, and suspension](#55-foreign-calls-blocking-and-suspension)
- [56. Callbacks and execution domains](#56-callbacks-and-execution-domains)
- [57. Foreign unwinding and failure](#57-foreign-unwinding-and-failure)

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

Application and embedding roots carry a root-only host/embedding contract in build/package/embedding metadata. The contract MUST identify scheduler/event integration sufficient to satisfy the runnable-strand progress rule of [§69.6](11-formal-semantics.md#696-cooperative-scheduler). It may additionally state:

- startup/entry-point shape;
- external effect/service implementations supplied by the host;
- finite-return/progress facts for host-driven waits where such facts justify absence of `diverge`;
- native adapter trust metadata;
- root lifecycle ownership.

These facts are not ordinary module requirements and are not propagated through library interfaces.

### 48.5 Root conformance

After ordinary semantic checking succeeds, the selected root contract is checked against the already-typed application/embedding root.

Root conformance is **not** an additional premise for ordinary expression typing. It cannot satisfy a missing trait, erase an effect, alter `Dup`/`Discard`, extend a region/taskgroup lifetime, or authorize an unsafe operation. Failure of root conformance rejects the executable/embedding configuration, not an otherwise valid ordinary library call. The formal judgment is summarized in [§58.7](11-formal-semantics.md#587-root-hostembedding-conformance).

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

The callback result and every value escaping the callback invocation MUST NOT retain `MarshalProvenance`. A type retaining that provenance is not `CaptureFree`, so it cannot be stored in `Ref` even within the callback ([§13.5](04-captures-and-access.md#135-retention-horizons)). Exclusive mutable owners remain subject to ordinary whole-owner capture and lexical non-escape checks. A nested taskgroup or other structural computation may use the temporary view only when its entire retained lifetime resolves before the marshalling callback returns; the fresh provenance prevents work or results tied to the view from escaping that boundary.

The pointer is therefore valid only for the callback's dynamic extent. The `MarshalProvenance` rule establishes the lifetime horizon of the safe view; it does not by itself prove physical address stability. The marshalling wrapper MUST separately ensure that any dereferenceable native address remains valid for the entire callback invocation, for example because the representation is already stable for that interval, by copying into temporary native storage, or by another audited implementation-private technique. Such implementation machinery does not create a source-level `Pin` property.

Raw-pointer extraction from the temporary view remains unsafe unless a narrower audited scoped operation proves validity automatically. Unsafe code that deliberately retains or exports a raw pointer past the marshalling horizon assumes the corresponding native lifetime proof obligation and is outside safe-language soundness. A safe marshalling wrapper MUST NOT expose a safe result whose correctness depends on such retention.

### 53.5 Native arenas

A general stable native arena is not a core-language primitive. Libraries MAY build scoped native arenas from unsafe/native allocation facilities when a concrete foreign graph/intrusive-data use case requires them.

Such an arena does not become an Eldude region merely because its allocations share a lifetime.

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

The callback contract MUST state invocation cardinality. A callback that may be skipped and abandoned requires a discardable callable environment; a skipped callback may instead be returned/transferred or consumed by an available specified structural-discharge operation under [§12.4](04-captures-and-access.md#124-higher-order-generic-constraints). One that may be invoked repeatedly requires a duplicable callable environment. The contract also states whether the same callback registration may be re-entered before a prior invocation returns. Re-entry of the same registration requires a duplicable callable environment because two live invocations may overlap. Re-entry through a distinct independently owned registration does not by itself duplicate the first callback value.

Such a callback is nested execution, not a new parallel Eldude strand. Active `view`/`mut` grants in the waiting Eldude/native call chain remain active during synchronous re-entry. The audited aliasing/reentrancy contract and the safe wrapper MUST therefore ensure that a re-entered callback cannot create a grant conflicting with an already active grant to the same mutable owner or native-backed storage.

An ordinary safe same-domain synchronous callback executes beneath an internal **foreign-control barrier** represented in the structural context `Control` ([§58.8](11-formal-semantics.md#588-foreign-control-barriers)). Under the ordinary barrier:

- the callback's residual callable contract MUST NOT admit `suspend`;
- execution MUST NOT reach an ordinary suspension point such as `await`, `task::yield()`, a suspending host/foreign wait, or structural cleanup whose residual contract admits `suspend`;
- algebraic handler lookup MUST NOT cross the barrier: every algebraic operation performed by the callback must be interpreted by a handler installed on the callback side of the waiting foreign frame, or the composition is rejected;
- the prohibition on crossing the barrier applies equally to `tail`, `once`, and `affine` operations. `NonAbandoning` is insufficient to relax this rule because `tail` and `once` do not abandon the continuation but may still require continuation capture and resumption;
- pending cooperative cancellation is not delivered through the foreign frame. Because the ordinary callback cannot suspend, a cancellation request remains pending until execution has returned through the foreign call and reaches an ordinary unmasked Eldude suspension point.

A function value whose public effect row admits `suspend` therefore cannot be used directly as an ordinary synchronous callback merely because a particular implementation path is expected not to suspend. Likewise, an opaque callback whose residual row contains an algebraic family must be wrapped so that the family is handled on the callback side of the barrier before callback return. These are separate-compilation rules over canonical callable contracts, not implementation-body inspection.

A safe adapter for a callback that can defect MUST provide a defect rendezvous. At the first transition into defect processing, before callback-local structural discharge or any further native call, the runtime records the defect and marks every active enclosing synchronous foreign invocation in the affected waiting call chain as defect-pending. It then performs callback-local structural unwinding according to the ordinary Eldude rules, prevents normal Eldude continuation of the failed callback, returns through the foreign frame using an ABI-valid private control path guaranteed by the audited native contract, and resumes Eldude defect unwinding only after control reaches an Eldude boundary. Any sentinel/status used solely for this rendezvous is adapter-internal and is not exposed as a normal recoverable application result. If the native API cannot guarantee such a rendezvous, the synchronous callback adapter is unsafe.

Each synchronous foreign invocation has an internal defect-pending state shared by callback entries through that invocation and its nested waiting native call chain. The state MUST be set when the defect first becomes pending, before any callback-local structural unwinding/native call, rather than only when unwinding reaches the barrier. Every active enclosing invocation is marked; after an inner invocation reaches rendezvous, enclosing invocations remain pending until their own Eldude boundaries are regained. Until the invocation reaches its Eldude rendezvous boundary, every further callback entry through the affected invocation MUST be suppressed: it executes no callback body, forms no Eldude grants, and returns only the audited ABI-valid private failure/control result. This applies to another registration as well as re-entry of the failed registration. The contract must make repeated suppressed entries valid for the native caller; otherwise the adapter is unsafe.

Already-required callback-local structural unwinding may continue; it does not authorize fresh normal callback work. Native calls made during that discharge must honor the same pending-state check. Suppression is invocation-scoped, not a domain-wide suspension of unrelated strands or registrations. A pending defect cannot be cleared by native success, callback retry, or returning an ordinary sentinel. At rendezvous the waiting Eldude computation resumes defect unwinding, never normal completion. The retained callback/registration obligations of a suppressed entry remain owned until their specified structural discharge; suppression does not count as a successful callback delivery or silently release roots. The rule also applies to audited stack-preserving protocols.

A host/native adapter MAY define a separately audited **stack-preserving synchronous callback protocol** that permits `suspend`. Such a protocol MUST specify at least native-stack/frame lifetime while parked, the thread/fiber on which resumption occurs, runtime rooting of managed values reachable from the parked computation, stability of retained dereferenceable native pointers, permitted reentrancy, cancellation rendezvous, defect rendezvous, and shutdown behavior. Under such a protocol, suspension uses the ordinary Eldude `suspend` and cancellation semantics; the exceptional protocol does not create a second suspension effect. Permission to suspend does not by itself permit an algebraic operation to target a handler outside the foreign-control barrier. Cross-foreign-frame algebraic continuation capture/resumption is not part of the ordinary safe FFI model.

### 56.2 Asynchronous callback from another native thread

Arbitrary native threads do not directly execute unrestricted Eldude code.

A safe retained callback arriving from another native thread is converted by the runtime/native shim into an event posted to the appropriate Eldude execution domain. The Eldude callback body executes later under ordinary single-domain scheduling. Posting does not grant the foreign thread an immediate synchronous Eldude result; a native API that requires such a result falls under [§56.3](#563-synchronous-arbitrary-thread-callback) unless a dedicated audited bridge defines the wait and runtime-attachment semantics.

The callback registration must have an explicit structured lifetime owner: a host root scope, a taskgroup-compatible wrapper, or another audited owner. Closing that owner MUST prevent acceptance of new callbacks according to the native contract, deregister the native callback, and drain or otherwise terminally account for already accepted/in-flight callback deliveries before captured Eldude state and rooting registrations are released. If the native API cannot provide a trustworthy lifetime/deregistration boundary, a bounded ordinary safe registration is not available; the callback must instead be owned by an appropriately long-lived host/native root or use an unsafe adapter.

Its audited complete-lifecycle cardinality ([§56.2.1](#5621-lifecycle-cardinality-and-undelivered-obligations)) determines the ordinary `Dup`/`Discard` requirements on the retained callback value; repeated delivery requires a duplicable callable environment. Runtime queueing, batching, and backpressure strategy are implementation/library choices, but observable dropping, coalescing, blocking, or bounded-queue failure is part of the adapter's public semantic contract.

### 56.2.1 Lifecycle cardinality and undelivered obligations

A retained callback's cardinality is measured over its complete registration lifecycle, including successful delivery, native cancellation, explicit close, owner cleanup, queue suppression/coalescing, and accepted/in-flight work. The contract MUST distinguish native event occurrence, accepted delivery, and actual invocation of the Eldude callable. An unconditional `exactly once` callable contract means one invocation before every normally completed lifecycle; an API whose close can suppress that invocation cannot advertise that unconditional guarantee.

At registration, ownership of each non-`Dup` callback instance transfers to exactly one lifecycle obligation. Posting transfers responsibility to one accepted delivery; it does not duplicate the registration's obligation. Close races with acceptance/delivery must select one owner and one terminal outcome. Native copies of a token and queue bookkeeping are not additional owned callback instances.

Every path that suppresses an undelivered callback MUST do one of the following, and its public ownership/effect contract must identify which:

- abandon it only when the complete callback environment satisfies `Discard`;
- return or transfer the uninvoked callback as an owned result/obligation, after deregistration and the required accepted/in-flight drain;
- consume it through a specified structural discharge protocol that accounts for every captured obligation. Generic dropping of a non-`Discard` closure is not such a protocol. Safe generic code cannot inspect an opaque function value to recover its captures; the callable representation/interface or an audited intrinsic must actually provide the discharge operation. A documented terminal cancellation invocation may discharge it when the callback signature admits that outcome.

For example, a consuming `cancel` may return `Option<Callback>`: `Some` returns the still-uninvoked instance, and `None` proves that invocation or the advertised structural discharge already owns/completed it. The adapter cannot report `None` merely because the native event was never delivered. A queued but unstarted callback must likewise be drained, recovered, or validly discharged rather than lost when the queue closes.

Canonical `Cleanup` returns `Unit` and therefore cannot use the callback-return alternative. A registration offering automatic close via `using` must require `Discard` for any callback it can abandon, or guarantee invocation/structural discharge during cleanup. Its cleanup row includes all callback/discharge/drain effects that may run, including `suspend` or `diverge` where applicable. A finite-return claim requires the corresponding terminal drain/discharge guarantee.

Once the callback is invoked, its ordinary callable-instance and control-exit rules govern its environment; the registration still owns native deregistration/rooting and drain responsibilities. Cancellation of an in-flight callback is not evidence that those responsibilities ended. Defect exits follow [§20](05-effects-and-failure.md#20-defects-and-assertions)'s best-effort structural semantics rather than promising normal exactly-once completion; pending-defect suppression ([§56.1](#561-same-domain-synchronous-callback)) never erases a live registration obligation.

### 56.3 Synchronous arbitrary-thread callback

A foreign API requiring Eldude code to execute synchronously on an arbitrary external thread with an immediate return value cannot use the general safe callback mechanism.

Supporting such an API requires a dedicated unsafe/native adapter with explicit runtime attachment, synchronization, rooting, callback-lifetime, and foreign-control semantics.

Eldude does not add `Send`/`Sync`-like predicates to all values merely to support this case.

## B.21 Synchronous foreign callback with callback-local algebraic control

Conceptually:

```eldude
effect Choice { tail choose() -> Bool; }

callNativeWithCallback(fn() {
    handle {
        !Choice::choose()
    } with handler Choice {
        choose() => true;
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
    choose() => true;
}
```

This composition is rejected for an ordinary synchronous callback in every operation mode. The matching handler lies outside the waiting foreign frame, and `NonAbandoning` does not authorize continuation capture/resumption through that frame.

## B.23 Rejected suspension in an ordinary synchronous callback

```eldude
callNativeWithCallback(fn() {
    task::yield()
});
```

The callback admits `suspend` and is rejected by the ordinary foreign-control barrier. A separately audited stack-preserving callback protocol may permit suspension, but it must satisfy [§56.1](#561-same-domain-synchronous-callback) and does not thereby permit algebraic control to cross the barrier.

## B.24 Retained foreign-thread callback registration

Conceptually:

```eldude
using (registration = ffi::registerPostedCallback(state, callback)?) {
    run();
}
```

This `using` form is valid only when callback skipping is `Discard`-permitted or cleanup guarantees invocation/structural discharge under [§56.2.1](#5621-lifecycle-cardinality-and-undelivered-obligations). The registration is a structured lifetime owner. Its cleanup/deregistration protocol prevents new delivery and drains or terminally accounts for accepted/in-flight posted callbacks before releasing retained Eldude captures or rooting handles.

## 57. Foreign unwinding and failure

Typed Eldude failure and algebraic control MUST NOT unwind through arbitrary foreign frames. Ordinary safe Eldude likewise does not permit a C++ exception, Rust/native unwind, `longjmp`, forced unwind, or equivalent native non-local transfer to skip live Eldude frames. Safe adapters catch, translate, or rendezvous such control at the audited boundary before ordinary Eldude execution continues.

A platform-specific host/native adapter MAY support a stronger cross-language unwind protocol only as an explicit audited trust boundary that preserves the Eldude structural obligations it crosses. Such support is not implied by an ordinary foreign declaration or calling convention and does not alter the portable safe-language semantics.

Safe adapters translate typed results/control outcomes at the boundary.

Assertion defects likewise MUST NOT unwind through arbitrary foreign frames. A safe synchronous callback adapter must use the defect-rendezvous protocol of [§56.1](#561-same-domain-synchronous-callback) so that Eldude structural unwinding resumes only after the audited foreign call regains an Eldude boundary. If the native call may fail to return after such a callback failure, that possibility contributes `diverge`.

A defect MUST NOT become a normal recoverable return to a still-live Eldude continuation. At the terminal root/embedding boundary, the host may report the ended Eldude execution to its native caller according to the root contract. That report neither clears a pending synchronous-callback defect nor resumes the failed Eldude execution; callback-local private sentinels remain rendezvous machinery under [§56.1](#561-same-domain-synchronous-callback).

---

[Specification index](../language-specification.md) · Previous: [9. Structured concurrency](09-concurrency.md) · Next: [11. Formal static and dynamic semantics](11-formal-semantics.md)
