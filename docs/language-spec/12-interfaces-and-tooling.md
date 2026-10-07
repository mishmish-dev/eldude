# Chapter 12 — Interfaces, compilation, and tooling

[Specification index](../language-specification.md) · Previous: [11. Formal static and dynamic semantics](11-formal-semantics.md)

This implementer reference defines the public information needed for separate compilation, native bindings, incremental checking, and diagnostics.

**Prerequisites:** [3. Traits and dynamic abstraction](03-traits.md), [4. Closures, captures, and scoped access](04-captures-and-access.md), [5. Effects, termination, and failure](05-effects-and-failure.md), [10. Host, unsafe code, and FFI](10-host-and-ffi.md), [11. Formal static and dynamic semantics](11-formal-semantics.md).

The numbered rules are normative under the [specification conventions](../language-specification.md). Examples are illustrative snippets; names and omitted bodies may stand for surrounding program or library context.

A canonical interface can publish a complete callable contract without its body. This is generated interface notation:

```text
module arithmetic;
pub fn add(x: Int, y: Int) -> Int;
semantic { result-captures <= {}; }
```

## In this chapter

- [71. Separate compilation](#71-separate-compilation)
- [72. Canonical semantic interfaces](#72-canonical-semantic-interfaces)
- [73. Generic compilation](#73-generic-compilation)
- [74. ABI and representation](#74-abi-and-representation)
- [75. Incremental checking](#75-incremental-checking)
- [76. Diagnostics](#76-diagnostics)
- [77. Formatting and source stability](#77-formatting-and-source-stability)
- [78. Testing](#78-testing)

## 71. Separate compilation

### 71.1 Semantic boundary

An ordinary module MUST be semantically checkable from exactly:

- its own source; and
- canonical semantic interfaces of its direct imports.

Imported implementation bodies MUST NOT be required for ordinary name resolution, type checking, effect checking, capture checking, usage checking, trait resolution, non-divergence checking, or region checking. An application or embedding root is additionally subject to the separate root-conformance judgment of [§58.7](11-formal-semantics.md#587-root-hostembedding-conformance); that judgment does not alter the semantic validity of imported ordinary library modules.

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
- effect rows preserving duplicate slots and their single open tail, plus canonical effect-family control summaries sufficient to derive continuation-control envelopes without requiring transitive implementation inspection;
- constraints on effect-row parameters, including intrinsic `NonAbandoning` constraints;
- callable-environment captures, result-capture bounds, and capture-row parameters;
- intrinsic `Dup` and `Discard` guarantees;
- intrinsic mutable-owner status where applicable;
- finite-completion facts for concrete iterator implementations;
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
result-capture bounds
finite positive storage parameter profiles when exported
mutable-owner status when exported
```

These facts are contracts, not implementation details.

### 72.4 Trait implementation index

Because implicit implementations are owned by the module defining the trait or nominal head type, the relevant module interface can export the canonical implementation headers needed for deterministic resolution.

The index MUST include canonical implementation heads, complete prerequisites, and associated/GAT equations needed by [§§10.6](03-traits.md#106-implicit-implementation-patterns-and-selection)–[10.8](03-traits.md#108-associated-equations-and-normalization), including dependencies required to interpret those headers. Method bodies are not consulted. Imported headers obey the same admissibility and overlap rules as local headers.

Import order MUST NOT create or remove an applicable implicit implementation.

### 72.5 Handler effects require no standalone interface object

Because handlers are lexical rather than first-class values, canonical interfaces contain no standalone `Handler<...>` value/type contracts.

A public function or method that installs a handler exports its ordinary function contract:

- parameter/result types;
- complete residual effect row after the handler has interpreted its family;
- captures/provenance and result-capture bounds;
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
    representation = opaque;
    usage { Dup = (T: Dup); Discard = (T: Discard); }
    result-captures <= {captures(cell), ..C, @r};
    mutable-owner-region = @r;
    finite-positive-parameters = {0, 1};
}
```

These clauses illustrate separate applicable subjects, not one declaration requiring every fact. `result-captures <= {...}` is the authoritative public upper-bound algebra of [§13.6](04-captures-and-access.md#136-canonical-interfaces-and-conservative-mutation). `mutable-owner-region = @r` states the intrinsic `MutableOwner<T,@r>` fact when clients may form root `mut` grants. `finite-positive-parameters` lists the zero-based generic parameter positions certified by [§8.5](02-types-and-ownership.md#85-finite-inductive-recursive-declarations); `{}` certifies no positions. `finite-iteration = true` applies only to a concrete `Iterator` implementation certified under [§35.5](08-collections.md#355-finite-iteration-and-non-divergence); omission offers no finite-completion guarantee. Storage positivity and finite iteration are distinct facts. FFI facts use the generated contracts and protocol descriptions of [§72.9](#729-generated-ffi-semantic-contracts).

Capture bounds use whole values only ([§13.6](04-captures-and-access.md#136-canonical-interfaces-and-conservative-mutation)). Mutable arguments use the uniform conservative post-call rule; no per-callable mutation or stored-payload contract is exported. A capture-free return such as `Unit` does not suppress those mutation checks.

`representation = complete` certifies that the rendered nominal fields/constructors are exhaustive. `representation = opaque` states that they are incomplete or unavailable: struct construction/decomposition cannot infer missing fields, and enum matching must account for the opaque remainder of [§5.3](01-foundations.md#53-exports-and-opacity). A semicolon struct implies `opaque`; a generated braced nominal declaration with omitted members MUST carry the marker. In the absence of a marker, a braced declaration is complete. An explicit contradictory marker is an interface error. Private member names and types are not serialized merely to explain this fact.

A generated `usage` block gives each intrinsic permission's public sufficient condition. `true` offers the permission unconditionally; `false` offers no such guarantee. A parenthesized comma-separated set of constraints is conjunction, and `|` between those sets is disjunction. The only permitted atoms are kind-correct public type equalities and intrinsic `Dup`/`Discard` bounds on types or capture rows. The condition may mention only the nominal declaration's public generic inputs and publicly nameable types; it introduces no user trait search, negative predicate, existential guess, or executable proof. A client gains a permission when at least one conjunction is established by the existing equality/usage judgments. Recursive conditions must be justified by the existing structural usage derivation, never by assuming the permission being established.

For example, an opaque `Box<T>` that stores `T` publishes `usage { Dup = (T: Dup); Discard = (T: Discard); }`, whereas a phantom representation may publish both permissions as `true`; a linear resource publishes both as `false`. These are permission conditions, not formation constraints: `Box<LinearResource>` remains a legal linear type. The defining module checks every offered condition against its representation and source-level strengthening. Opaque declarations MUST publish both conditions; unavailable hidden proofs may conservatively withhold a guarantee, but cannot grant one. Complete representations may derive the same facts directly. An interface usage block is not an `impl Dup`/`impl Discard` declaration and is unreachable from ordinary source. Changing a published condition changes the semantic interface.

Other future generated clauses MUST use source-level semantic terminology and MUST NOT expose implementation-specific solver state as the only representation of a client-relevant fact.

A semantic block is attached to its preceding declaration. Nested `member(path) { ... }` clauses select individual methods, fields, associated declarations, or enum constructors by canonical identity; this includes trait and implementation methods and declarations in an `extern` block. Nested `parameter(n)`, `result`, and `component(n)` clauses select callable slots and stored tuple/payload components with the same zero-based rules as [§72.9](#729-generated-ffi-semantic-contracts). They remain available for nested callable, usage, and FFI contracts, but do not refine stored-value capture summaries. `result-captures` applies only to a callable subject and bounds that callable's whole result. Repeated selectors or facts in the same scope, invalid member/slot identities, or facts inappropriate to that subject are interface errors. Selectors use [§72.9](#729-generated-ffi-semantic-contracts)'s canonical recursive ordering.

Within a selected callable contract, `captures(x)` refers to the whole named parameter/accessed-value summary. The positional spelling `captures(parameter(n))` refers to its zero-based parameter summary (counting a receiver), and `captures(..)` refers to the whole callable environment. Sources have no projection suffix. Canonical rendering uses positional parameter sources. Selecting a nested callable starts a new parameter/environment scope; its bound describes its own return, and cannot refer implicitly to the enclosing callable's arguments. The bound's meaning and transitive provenance rules remain those of [§13.6](04-captures-and-access.md#136-canonical-interfaces-and-conservative-mutation).

Generated semantic clauses are interface/diagnostic notation. They belong to the `interface_file` entry point of the [formal grammar](../formal-grammar.md), not to the ordinary Eldude source grammar. A generated interface is therefore not promised to be a copy-pastable source stub unless those interface-only clauses are omitted. Tools MUST label/render canonical interface output distinctly enough that interface-only syntax is not presented as ordinary author-written source.

These clauses do not create new user-denotable values, lifetime inequalities, capabilities, or author-written requirements.

### 72.8 Canonicalization and hashing

Interfaces SHOULD have a deterministic canonical serialization suitable for content hashing.

Equivalent public semantics should produce the same semantic interface representation independent of private declaration order or source formatting.

### 72.9 Generated FFI semantic contracts

Every client-relevant audited native fact required by [§74.4](#744-canonical-native-binding-metadata) MUST appear in a generated `ffi-contract { ... }` inside the declaration's `semantic { ... }` block. Ordinary types, effects, captures, and `Cleanup` remain part of the interface; the FFI clauses record the additional audited obligations and guarantees. These clauses are interface-only notation, never author-written source annotations. Mechanically derived symbol/calling-convention/layout facts remain in the separate ABI representation of [§74.2](#742-public-abi).

A contract describes its attached declaration. `parameter(n) { ... }` selects zero-based callable parameter position, counting a receiver when present; `result { ... }` selects its result. `member(path) { ... }` selects a member by canonical identity, including a function in an `extern` block, a method/field, or an enum constructor/record-payload field of an exported nominal declaration. `component(n) { ... }` selects a zero-based stored tuple or positional constructor-payload component; selecting an enum constructor with `member` first distinguishes its payload from other variants. These selectors may nest to locate contracts on callback arguments/results or aggregate members. Within a selected subject, `pointer`, `output`, `callback`, and `marshalling` blocks distinguish the following applicable facts. Source parameter names are display labels, not contract identities.

The following vocabulary is normative. Values in the table are bare generated words, except capture bounds and `protocol(path)` references. `not_applicable` is permitted only when the fact genuinely does not apply; it is not an unknown guarantee. Unknown/unproved facts MUST be rendered as `unverified` where admitted or as an explicit unsafe precondition described by a protocol, rather than omitted to suggest safety.

| Subject | Keys, in canonical order | Values/meaning |
|---|---|---|
| Callable/native operation | `invocation` | `synchronous`, `offloaded`, `posted` |
| Callable/native operation | `blocking` | `none`, `may_block` |
| Callable/native operation | `finite-return` | `guaranteed`, `unverified`; the latter contributes `diverge` under [§55](10-host-and-ffi.md#55-foreign-calls-blocking-and-suspension) |
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
| Callback | `cardinality` | `may_skip` (zero or one), `exactly_once` (one), `may_repeat` (zero or more), or `protocol(path)` for other minimum/maximum or conditional bounds; measured over the complete lifecycle ([§56.2.1](10-host-and-ffi.md#5621-lifecycle-cardinality-and-undelivered-obligations)) |
| Callback | `reentrancy` | `forbidden`, `permitted`, or `protocol(path)`; permission is per registration |
| Callback | `thread-affinity` | `same_domain_thread`, `posted_to_domain`, `audited_attached_thread`, or `protocol(path)` |
| Callback | `delivery-domain` | `current_domain`, `registration_domain`, or `protocol(path)` |
| Callback | `barrier` | `ordinary`, `stack_preserving`, `not_applicable`; `stack_preserving` requires the complete audited [§56.1](10-host-and-ffi.md#561-same-domain-synchronous-callback) protocol |
| Callback | `suspension` | `forbidden`, `permitted`; permission does not authorize crossing an ordinary barrier |
| Callback | `algebraic-crossing` | `forbidden` |
| Callback | `cancellation` | `deferred`, `ordinary_points`, or `protocol(path)` |
| Callback | `defect` | `rendezvous` or `protocol(path)` describing the applicable Eldude-boundary/private-ABI protocol |
| Callback | `pending-defect-entry` | `suppressed` for synchronous entry; `not_applicable` for independently posted delivery |
| Callback | `deregistration`, `drain` | each `not_applicable` or `protocol(path)` specifying the prevention-of-acceptance and accepted/in-flight terminal obligations |
| Callback | `undelivered` | `discard`, `return_obligation`, `structural_discharge`, `not_applicable`, or `protocol(path)` covering the possible lifecycle outcomes of [§56.2.1](10-host-and-ffi.md#5621-lifecycle-cardinality-and-undelivered-obligations) |
| Callback or lifetime owner | `shutdown` | `not_applicable` or `protocol(path)` |
| Any subject | `preconditions` | `protocol(path)` for additional audited validity, representation, encoding, lifetime, thread, or unsafe obligations |

Every applicable key MUST be emitted, including conservative ordinary-barrier facts. In addition to the listed scalar values, every key except the fixed `algebraic-crossing = forbidden` permits `protocol(path)` to describe compound/conditional behavior. The protocol MUST enumerate the alternatives and their guards/selection conditions; each alternative obeys the unconditional safe-language laws of [§§53](10-host-and-ffi.md#53-foreign-storage-and-identity)–[56](10-host-and-ffi.md#56-callbacks-and-execution-domains). This covers a callable that invokes inline on one path and posts/offloads on another, including the corresponding barrier, suspension, and pending-entry modes. It must not choose one scalar outcome that hides another. A protocol may supplement a fixed enum via `preconditions`; it cannot contradict that enum or relax a mandatory safe-language rule. Invalid scopes, repeated keys/selectors, invalid values, mismatches with the ordinary signature/effect row, or insufficient audited safety guarantees are interface errors.

Fixed callback facts have one source: the normalized callback-entry profile. For an ordinary synchronous entry, derive `barrier=ordinary`, `suspension=forbidden`, `cancellation=deferred`, and `pending-defect-entry=suppressed`. An audited stack-preserving synchronous entry derives the corresponding permitted-suspension/ordinary-cancellation profile and still suppresses entry after a pending defect. Independently posted delivery has no waiting foreign barrier or synchronous pending-entry state and executes with ordinary cancellation points. Every profile derives `algebraic-crossing=forbidden` in this version. Conditional protocols normalize each alternative separately. The renderer emits these derived facts for review, but metadata producers do not independently assert or override them. Canonical hashing uses the normalized profile and its deterministic expansion. Cardinality, reentrancy, lifetime, pointer stability, rendezvous details, and drain/discharge protocols remain independent audited facts.

A protocol reference names a stable canonical contract identity. The same semantic block MUST include exactly one `ffi-protocol path = "description";` for every referenced protocol, and descriptions must be self-contained with respect to their audited protocol behavior. Descriptions normalize line endings to LF; their remaining text is contract content, not subject to a prose-equivalence solver. The normalized description is part of the audited semantic contract and machine metadata, and MUST render all remaining client-relevant facts faithfully in human-readable terms; an opaque identifier/hash alone is insufficient. For a stack-preserving protocol this includes all [§56.1](10-host-and-ffi.md#561-same-domain-synchronous-callback) obligations, and for a retained registration it includes the terminal drain/discharge outcomes of [§56.2.1](10-host-and-ffi.md#5621-lifecycle-cardinality-and-undelivered-obligations). Tools may display the escaped string as prose, but must preserve its content in canonical serialization and semantic diffs. A changed guarantee, obligation, or protocol description invalidates semantic dependents independently of ABI changes.

Canonical rendering emits properties in the table's key order (a shared key appears once at its applicable subject), then subject blocks in the order `parameter`, `result`, `member`, `component`, `pointer`, `output`, `callback`, `marshalling`. Parameter/component selectors sort by numeric index, member selectors by canonical identity, recursively. Protocol descriptions follow the contract, sorted by canonical identity. Capture bounds use [§77](#77-formatting-and-source-stability)'s ordering. The same normalized metadata MUST produce the same keys, selector identities, protocol identities/descriptions, and order independently of source labels or input metadata order.

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

The `exactly_once` clause describes normally completed lifecycles; defects still follow [§§20](05-effects-and-failure.md#20-defects-and-assertions) and [56](10-host-and-ffi.md#56-callbacks-and-execution-domains). The protocol description supplies the audited control path behind the `defect` clause, not a recoverable application result.

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

The standard toolchain MUST define a deterministic machine-readable representation for imported/generated native contracts. It must keep mechanically derived ABI facts distinct from audited semantic facts and be capable of representing at least the categories required by [§§52](10-host-and-ffi.md#52-foreign-declarations)–[57](10-host-and-ffi.md#57-foreign-unwinding-and-failure): ownership transfer; pointer retention, mutability, aliasing, and stable-address requirements; output initialization; callback lifetime, cardinality, per-registration reentrancy, thread affinity, and delivery domain; ordinary versus audited-stack-preserving synchronous-callback mode; foreign-control-barrier behavior; callback suspension permission; cancellation rendezvous; blocking/offload classification; finite-return/`diverge` contract; defect rendezvous; foreign exception/unwind policy; deregistration/in-flight-drain behavior; and scoped temporary-marshalling lifetime/provenance.

An ordinary synchronous callback declaration canonically means the conservative [§56.1](10-host-and-ffi.md#561-same-domain-synchronous-callback) foreign-control barrier unless its audited host/native contract explicitly selects the stack-preserving exceptional protocol. No metadata default may imply support for cross-foreign-frame algebraic continuation transfer.

Generated Eldude interfaces MUST render every client-relevant audited fact using ordinary types, effects, captures, `Cleanup`, unsafe preconditions, and the complete generated FFI clauses/protocol descriptions of [§72.9](#729-generated-ffi-semantic-contracts). In particular, the metadata includes pending-defect entry suppression and complete-lifecycle undelivered-callback obligations ([§§56.1](10-host-and-ffi.md#561-same-domain-synchronous-callback)–[56.2.1](10-host-and-ffi.md#5621-lifecycle-cardinality-and-undelivered-obligations)). Tooling SHOULD support semantic diffing so a change to an audited contract is reviewable independently of an unchanged C ABI. This is tooling/interface structure, not a new source-language capability system.

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

Compiler-generated public signatures MUST use the same canonical surface conventions as the formatter, including one final `| e` tail for an open effect row and ordinary `where e: NonAbandoning` spelling for the intrinsic effect-row constraint. They MUST also include the human-readable generated semantic clauses required by [§72.7](#727-human-readable-semantic-interface-rendering) whenever a client-validity fact such as result provenance or mutable-owner status is not otherwise visible in the ordinary signature.

Generated canonical interfaces MUST render semantically unordered collections in one deterministic textual order:

- applied algebraic effect families sort by canonical fully qualified identity and then recursively canonicalized generic arguments; nominal error alternatives sort by canonical identity;
- `state<@r>` entries sort by canonical region-binder identity/order rather than incidental source spelling;
- duplicate effect labels are preserved, with same-family instance evidence in lexical nearest-to-outer order; any open row has exactly one tail, rendered after `|` following all fixed entries;
- intrinsic effect entries follow named/state entries in the fixed order `suspend`, then `diverge`;
- generated capture/provenance unions sort whole sources by canonical source slot (callable environment, then arguments by position); source names are replaced by positional parameter sources and duplicate entries are removed. Explicit provenance atoms follow by category and canonical binder/identity order, then capture-row variables by binder order;
- unordered constraint collections sort first by constrained binder order and then by canonical predicate identity;
- generated finite-positive parameter index sets sort in ascending parameter-position order.

Within a semantic subject, render representation and usage facts first, then result captures, mutable-owner region, finite-positive parameters, finite iteration, FFI facts, and nested selectors in [§72.9](#729-generated-ffi-semantic-contracts)'s order. A usage block renders `Dup` before `Discard`; sort atoms in each conjunction by the ordinary canonical constraint order, deduplicate them, then sort/deduplicate conjunctions lexicographically and remove any conjunction strictly containing another. An empty conjunction is `true`; no offered conjunction is `false`. These are fixed syntactic normalization rules, not arbitrary logical/prose equivalence solving.

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

---

[Specification index](../language-specification.md) · Previous: [11. Formal static and dynamic semantics](11-formal-semantics.md)
