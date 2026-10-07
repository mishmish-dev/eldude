# Eldude Standard Library

[Documentation and project map](index.md) · [Module/API map](../stdlib/README.md)

**Status:** working library profile, partially implemented.

The collection commitments below are normative for the bundled library, as referenced by [§32](language-spec/08-collections.md#32-standard-sequence-abstractions). The [language specification](language-specification.md) remains authoritative for ownership, effects, captures, termination, and control flow.

## Collection profile

| Type | Representation and purpose | Required costs |
| --- | --- | --- |
| `List<T>` | Default finite immutable dynamic-length sequence, contiguous logical element storage, value semantics, copy-on-write or equivalent retained sharing when usage permits | O(1) length and indexed location; amortized O(1) append when storage can be reused; O(n) worst-case copying on retained sharing or growth |
| `TreeList<T>` | Immutable persistent tree-backed sequence for branching historical versions | Logarithmic indexed update/access under a fixed branching-factor contract |
| `LinkedList<T>` | Finite immutable `Nil` / `Cons { head, tail }` structure | O(1) prepend, head, tail; O(n) length and indexed access |
| `Array<T,N>` | Immutable statically sized contiguous storage; `N` is a `NatIndex` | O(1) length and indexed location; shape-changing insertion/removal is outside the initial API |
| `DynArray<T,@r>` | Mutable growable contiguous storage owned in `@r`, never `Dup` | Freezing consumes the owner; allocation reuse is permitted when sound |

List literals always construct `List`; they do not contextually construct `Array`. A shared representation never grants a semantic copy of a non-`Dup` element. Collection usage and failure ownership follow specification [§§33](language-spec/08-collections.md#33-collection-usage)–[35](language-spec/08-collections.md#35-iteration): a fallible consuming operation must preserve all non-discardable inputs on every recoverable outcome.

Owning overlapping immutable slices may be added with explicit usage bounds, ordinarily `T: Dup + Discard`. They are not borrowed views into mutable storage. `Map` and `Set` use explicit equality/hash/order policies and have no dedicated literals. Text APIs distinguish UTF-8 bytes, Unicode scalars, and grapheme clusters; `Text` never silently converts to a foreign pointer. Numeric conversion uses typed operations, not a general cast operator. A reusable pure `Lazy<T>` requires `T: Dup`; ordinary function values already represent effectful delayed work. These policies retain specification [§§34.4](language-spec/08-collections.md#344-owning-immutable-subviews), [36](language-spec/08-collections.md#36-maps-sets-text-and-numeric-policy), and [37](language-spec/08-collections.md#37-laziness-policy) without adding new core mechanisms.

## Implementation order

The initial sequence was values and pure transformations, consuming sequences, regional state, cleanup, then structured concurrency. The corresponding [examples](../examples/README.md) now execute. Expand the API from concrete program needs; hash collections, text segmentation, streams, timers, native IO, and concurrent mapping remain later work.

## Initial API and builtin bindings

The [stdlib module map](../stdlib/README.md) distinguishes source implementations from declarations requiring interpreter primitives or further work. The declared API is only partly implemented. The bundled profile uses these canonical identities for existing language hooks:

| Language hook | Library identity |
| --- | --- |
| Optional access and `??` | `core::option::Option<T>` |
| `?` and `try` | `core::result::Result<E,T>`, error first |
| List literal | `collections::list::List<T>` |
| `for` | `core::iter::Iterator` and `core::iter::Next<I,T>` |
| `using` | `core::cleanup::Cleanup<!e>` |
| `spawn`, `await`, cancellation handle | `task::Task<T>` |

These are builtin bindings to ordinary library declarations or existing intrinsic protocols, not implicit imports of their source names. User modules still import the names they use. An identically spelled user type does not acquire these hooks. The nominal names of `Ref` and `DynArray` are library policy; their audited aliasable-cell and mutable-owner profiles supply the core semantics of specification [§§9.5](language-spec/02-types-and-ownership.md#95-mutable-owner-status) and [28](language-spec/07-state-and-cleanup.md#28-mutable-abstractions).

## Usage and provenance contracts

The following facts must accompany the eventual canonical interfaces; a semicolon type declaration alone is not a complete interface. Source implementations must prove the facts they export; runtime primitives require the corresponding audit. All capture bounds use specification [§13.6](language-spec/04-captures-and-access.md#136-canonical-interfaces-and-conservative-mutation)'s public algebra.

| Type | `Dup` guarantee | `Discard` guarantee | Stored provenance |
| --- | --- | --- | --- |
| `Option<T>` | `T: Dup` | `T: Discard` | Selected payload |
| `Result<E,T>` | `E: Dup` and `T: Dup` | `E: Discard` and `T: Discard` | Selected error/success payload |
| `Next<I,T>` | `I: Dup` and `T: Dup` | `I: Discard` and `T: Discard` | Item and successor state |
| `LinkedList<T>` | `T: Dup` | `T: Discard` | Finite visible recursive storage |
| `List<T>` | `T: Dup` | `T: Discard` | Whole-value summary of retained contents; no intrinsic allocation-region identity |
| `DynArray<T,@r>` | Never | `T: Discard` | Whole-value summary including contents and owner `@r` |
| `Ref<T,@r>` | Always for a well-formed cell | Always for a well-formed cell | Aliasable identity `@r`; payload obeys the fixed retention horizon |
| `Task<T>` | Never | Always for a well-formed task | Group identity and result provenance |

`Ref<T,@r>` and `Task<T>` require `T: Discard` for formation. No ownership obligation is discharged just by copying a representation. Empty construction retains no element values, but intrinsic type/owner dependencies remain: an empty `DynArray<T,@r>` retains `@r`. The audited `List<T>` profile proves it is capture-free when `T` is capture-free; it carries no additional hidden obligation. `DynArray` exports `mutable-owner-region = @r`. No separate payload capture profile is exported. Pure algebraic types above have finite positive storage parameters under specification [§8.5](language-spec/02-types-and-ownership.md#85-finite-inductive-recursive-declarations); `List` exports the audited profile `{0}`. Neither aliasable cells, tasks, nor mutable owners certify a finite positive storage parameter merely because their current payload happens to be finite.

For methods below, parameter 0 is `self`; other positions count left to right. `S` means the whole `captures(parameter(0))`, `V` the inserted value's whole summary, and `C` the callback's whole summary. These are explanatory abbreviations; interfaces render whole parameter sources. All bounds include dependencies required by the result type, and normalize to empty for a provably capture-free instantiated result ([§13.4](language-spec/04-captures-and-access.md#134-conservative-result-capture-bounds)).

| Operation | Result and mutation obligations |
| --- | --- |
| `List::new` | No retained element values; pure |
| `List::length` | Capture-free `Nat`; pure |
| `List::push` | Consumes source and value; whole result bound `S ∪ V` |
| `List::get` | Requires `T: Dup`; `Some` owns a semantic copy; whole result bound `S` |
| `List::remove` | Success returns removed value and remainder; failure returns bounds error and the entire original source; whole result bound `S` |
| `List::replace` | Success returns displaced value and updated source; failure returns bounds error, original source, and incoming value; whole result bound `S ∪ V` |
| `List::with` | Invalid index skips the callback and returns `None`; valid index projects one call-scoped `view`, invokes once, and returns `Some`; whole result bound `S ∪ C` |
| `List::filter` / `partition` | Visit in source order and preserve order in outputs; `filter` discards rejected elements; `partition` returns `(accepted, rejected)` preserving every element; whole result bound `S` |
| `List::next` | Empty returns `Done`; otherwise transfers first element and tail; whole result bound `S`, with no discarded elements |
| `DynArray::push` | Appends at the end; receiver keeps `S` and conservatively accumulates `V` under [§13.6](language-spec/04-captures-and-access.md#136-canonical-interfaces-and-conservative-mutation) |
| `DynArray::pop` | Empty returns `None`; otherwise transfers the last element; result bound `S`, and surviving receiver keeps `S` |
| `DynArray::freeze` | Consumes owner, preserves element order; result bound `S`, including `@r`, unless `T` is provably capture-free |
| `Ref::replace` / `set` | Install value only if its provenance meets `@r`'s retention horizon; `replace` returns old payload, `set` discards it using `T: Discard` |

All indices are zero-based. Negative indices and indices at or beyond length are out of bounds. `get`/`with` return `None`; `remove`/`replace` return `Err` with every consumed input intact. These expected bounds failures do not raise defects. `BoundsError` stores the attempted `Int` index and original `Nat` length. `DynArray` operations admit `state<@r>`, including observation and freezing; region elimination removes that effect only after escape checking succeeds.

For example, `freeze` exports `result-captures <= {captures(parameter(0))}`. With `T = Int`, the capture-free `List<Int>` result may leave `@r`; with a capture-bearing element type, the whole source bound remains even if the actual elements retain only outer scopes. This rule also applies through generic wrappers. There are no per-method mutation summaries: every exclusive mutable call, including an imported wrapper returning `Unit`, applies [§13.6](language-spec/04-captures-and-access.md#136-canonical-interfaces-and-conservative-mutation)'s conservative whole-owner union on all continuing exits. Removal does not shrink that summary. A cell write separately enforces [§13.5](language-spec/04-captures-and-access.md#135-retention-horizons)'s fixed horizon, so aliasing cannot hide a shorter-lived capture.

`List`'s and `LinkedList`'s concrete `Iterator` implementations export `finite-iteration = true`. The former uses the audited finite-length decrement; the latter's `Item` successor is its strict stored tail. An arbitrary implementation of `Iterator` has no such guarantee. This is independent of the finite positive storage profile used for recursive type formation.

`Cleanup` retains the canonical masked discharge rules of specification [§30](language-spec/07-state-and-cleanup.md#30-cleanup). `Task::cancel` consumes the handle, requests cancellation, and neither waits nor suspends. `yield` creates an ordinary cancellation/scheduling point. `join2` owns one nested taskgroup, transfers each supplied callable into one child, and returns `(leftResult, rightResult)` after both complete. There is no ordering guarantee between child effects. Residual effects, inherited-handler eligibility, defects, cancellation, drain, and result provenance follow the existing taskgroup rules. Its returned pair retains the corresponding callable result provenance; the group's own identity never escapes. Producer termination evidence is local checker information: awaiting an opaque task conservatively admits `diverge` under specification [§42.3](language-spec/09-concurrency.md#423-termination-dependency), rather than assuming an unpublished producer guarantee.

## Deliberate initial limits

The initial API omits overload families and convenience wrappers. `LinkedList::length` consumes its input and needs `T: Discard`; unrestricted inspection may be added later. `TreeList`, `Array`, maps/sets, text segmentation, IO, timers, and broader iterator adapters retain their profile commitments but do not yet have source API drafts. Cost guarantees remain unbenchmarked, and the experimental interpreter does not establish complete library conformance.
