# Initial Eldude standard-library API

[Documentation and project map](../docs/index.md) · [Library contracts](../docs/standard-library.md) · [Executable examples](../examples/README.md)

The `.eld` files are ordinary source declarations and bodies. The interpreter executes the subset needed by the positive examples: source functions such as `task::join2` run checked bodies; opaque collection, cell, and task operations use explicit primitives. Other declarations still need implementations. These files are not generated canonical interfaces and do not supply all semantic metadata required by [§72](../docs/language-spec/12-interfaces-and-tooling.md#72-canonical-semantic-interfaces).

The [library profile](../docs/standard-library.md) owns representation, cost, ownership, and intrinsic contracts. Declared module identities, rather than filesystem names, define imports; there is no package manifest or additional resolution mechanism.

| Module | Initial surface | Implementation status |
| --- | --- | --- |
| [core::option](core/option.eld) | `Option`, `isSome`, `map`, `andThen` | Ordinary source bodies |
| [core::result](core/result.eld) | `Result<E,T>`, `isOk`, `map`, `mapError`, `andThen` | Ordinary source bodies |
| [core::iter](core/iter.eld) | `Next<I,T>`, ownership-threaded `Iterator` | Trait and data declarations |
| [core::cleanup](core/cleanup.eld) | `Cleanup<!e>` | Existing intrinsic protocol |
| [collections::linked_list](collections/linked_list.eld) | `LinkedList`, `prepend`, consuming `length`, `next` | Ordinary source bodies |
| [collections::list](collections/list.eld) | `List`, bounds errors, lookup, push, remove, replace, inspection, filter, partition, `next` | Opaque representation and method contracts |
| [state::ref](state/ref.eld) | Regional `Ref`, `new`, `get`, `replace`, `set` | Cell primitives; `set` has a source body |
| [collections::dyn_array](collections/dyn_array.eld) | `DynArray`, `new`, `length`, `push`, `pop`, `freeze` | Mutable-owner primitives |
| [task](task.eld) | `Task`, `cancel`, `yield`, `join2` | Runtime primitives; `join2` has a source body |

Callbacks used by `Option`/`Result` transformations may be skipped, so their environments must be `Discard`. They need no `Dup` guarantee because each selected callback runs once. Collection filtering/partitioning may skip and repeat their predicate, so its environment needs both permissions. `filter` additionally needs `T: Discard`; `partition` preserves all elements. Initial collection predicates are pure. These are ordinary usage rules, not new callback modes.

Capture contracts use whole arguments and environments. Mutable calls conservatively accumulate captures in surviving owners. A frozen `DynArray` may leave its allocation region only when its element type is provably capture-free; the [library profile](../docs/standard-library.md#usage-and-provenance-contracts) defines the bounds, including their application through wrappers.

The initial API omits `unwrap`, implicit cleanup, detached tasks, borrowed collection views, and effectful module initializers. Executable example coverage does not imply complete API coverage.
