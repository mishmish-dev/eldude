# Eldude Standard Library

Version: 0.0.3 working profile

The collection commitments below are normative for the bundled library. They were previously embedded in language specification §32. The [language specification](ELDUDE-LANGUAGE-SPECIFICATION.md) remains authoritative for ownership, effects, captures, termination, and control flow.

## Collection profile

| Type | Representation and purpose | Required costs |
| --- | --- | --- |
| `List<T>` | Default finite immutable dynamic-length sequence, contiguous logical element storage, value semantics, copy-on-write or equivalent retained sharing when usage permits | O(1) length and indexed location; amortized O(1) append when storage can be reused; O(n) worst-case copying on retained sharing or growth |
| `TreeList<T>` | Immutable persistent tree-backed sequence for branching historical versions | Logarithmic indexed update/access under a fixed branching-factor contract |
| `LinkedList<T>` | Finite immutable `Nil` / `Cons { head, tail }` structure | O(1) prepend, head, tail; O(n) length and indexed access |
| `Array<T,N>` | Immutable statically sized contiguous storage; `N` is a `NatIndex` | O(1) length and indexed location; shape-changing insertion/removal is outside the initial API |
| `DynArray<T,@r>` | Mutable growable contiguous storage owned in `@r`, never `Dup` | Freezing consumes the owner; allocation reuse is permitted when sound |

List literals always construct `List`; they do not contextually construct `Array`. A shared representation never grants a semantic copy of a non-`Dup` element. Collection usage and failure ownership follow specification §§33–35: a fallible consuming operation must preserve all non-discardable inputs on every recoverable outcome.

Owning overlapping immutable slices may be added with explicit usage bounds, ordinarily `T: Dup + Discard`. They are not borrowed views into mutable storage. `Map` and `Set` use explicit equality/hash/order policies and have no dedicated literals. Text APIs distinguish UTF-8 bytes, Unicode scalars, and grapheme clusters; `Text` never silently converts to a foreign pointer. Numeric conversion uses typed operations, not a general cast operator. A reusable pure `Lazy<T>` requires `T: Dup`; ordinary function values already represent effectful delayed work. These policies retain specification §§34.4, 36, and 37 without adding new core mechanisms.
