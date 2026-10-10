# Initial Eldude standard-library API

[Documentation and project map](../docs/index.md) · [Library contracts](../docs/standard-library.md) · [Executable examples](../eldude-program-examples/README.md)

The `.eld` files contain executable source declarations and bodies. Bundled bodies pass through the same parser, checker, and interpreter as user code, including unused and generic bodies. Bodyless primitives have explicit compiler/runtime bindings. These files are not generated canonical interfaces and do not supply all semantic metadata required by [§72](../docs/language-spec/12-interfaces-and-tooling.md#72-canonical-semantic-interfaces).

The [library profile](../docs/standard-library.md) owns representation, cost, ownership, and intrinsic contracts. Declared module identities, rather than filesystem names, define imports; there is no package manifest or additional resolution mechanism.

| Module | Initial surface | Implementation status |
| --- | --- | --- |
| [core::option](core/option.eld) | `Option`, `isSome`, `map`, `andThen` | All methods execute checked source bodies |
| [core::result](core/result.eld) | `Result<T,E>`, `isOk`, `map`, `mapError`, `andThen` | All methods execute checked source bodies; propagation is intrinsic |
| [core::iter](core/iter.eld) | `Next<I,T>`, ownership-threaded `Iterator` | `for` uses checked `next` implementations; finite stored-subterm steps and primitive `List` iteration need no `diverge` |
| [core::cleanup](core/cleanup.eld) | `Cleanup<!e>` | Intrinsic protocol; user implementation bodies are checked and executed |
| [collections::linked_list](collections/linked_list.eld) | `LinkedList`, `prepend`, consuming `length`, `next` | All three methods execute checked source bodies |
| [collections::list](collections/list.eld) | `List`, bounds errors, lookup, push, remove, replace, inspection, filter, partition, `next` | All declared methods have explicit primitive contracts; bounds failures return every owned input |
| [state::ref](state/ref.eld) | Regional `Ref`, `new`, `get`, `replace`, `set` | `CaptureFree + Discard` payload admission; primitive `new`/`get`/`replace`; checked source `set` |
| [collections::dyn_array](collections/dyn_array.eld) | `DynArray`, `new`, `length`, `push`, `pop`, `withMut`, `freeze` | Mutable-owner primitives and conditional grant projection |
| [task](task.eld) | `Task`, `cancel`, `yield`, `join2` | Scheduler bindings for `cancel`/`yield`; `join2` executes its checked source body |

Both `task::yield` and the fixture host's `eldude::fixture::yield` bind to cooperative scheduler suspension. Source acceptance and rejection programs cover the declared API. `List` uses shared array ranges for amortized O(1) append along the latest version and O(1) iteration steps; branching append copies the visible range. See the [implementation limits](../docs/implementation.md#implementation-limits) for storage retention and interpreter bounds.

Callbacks used by `Option`/`Result` transformations may be skipped, so their environments must be `Discard`. They need no `Dup` guarantee because each selected callback runs once. Collection filtering/partitioning may skip and repeat their predicate, so its environment needs both permissions. `filter` additionally needs `T: Discard`; `partition` preserves all elements. Initial collection predicates are pure. These are ordinary usage rules, not new callback modes.

Capture contracts use whole arguments and environments. Mutable calls conservatively accumulate captures in surviving owners. A frozen `DynArray` may leave its allocation region only when its element type is provably capture-free; the [library profile](../docs/standard-library.md#usage-and-provenance-contracts) defines the bounds, including their application through wrappers.

The `Ref<T,@r>` payload bound is `T: CaptureFree + Discard`. The checker derives this property from supported structural types or explicit generic/existential evidence. Cells cannot hold scoped references, tasks, or closures with scoped dependencies, even within the same region.

The initial API omits `unwrap`, implicit cleanup, detached tasks, borrowed collection views, and effectful module initializers. Executable example coverage does not imply complete API coverage.
