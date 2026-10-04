# Initial Eldude standard-library API

This is a small working API draft for the bundled 0.0.4 profile. The `.eld` files contain ordinary source declarations, with implementations for pure operations where practical. Opaque types and bodyless functions still need compiler/runtime backing or library implementations. They are not generated canonical interfaces and cannot substitute for the complete semantic metadata required by specification [§72](../docs/language-spec/12-interfaces-and-tooling.md#72-canonical-semantic-interfaces). The source runner resolves these modules and executes the subset needed by all 49 positive examples. Source functions such as `task::join2` execute through the checked interpreter; opaque collection, cell and task operations use explicit interpreter primitives. The entire declared API is not yet implemented.

The [standard-library profile](../docs/standard-library.md) records representation, cost, ownership, and intrinsic contracts. The [example programs](../examples/README.md) supply incremental implementation targets. Source module declarations, not filesystem names, define import identities; no package manifest or new package-resolution mechanism is introduced here.

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

No `unwrap`, implicit cleanup, detached task, borrowed collection view, or effectful module initializer is introduced. All staged value, ownership, result, effect, state/collection and task examples now execute. Remaining API coverage is separate from this example milestone.
