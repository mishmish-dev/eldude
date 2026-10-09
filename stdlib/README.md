# Initial Eldude standard-library API

[Documentation and project map](../docs/index.md) · [Library contracts](../docs/standard-library.md) · [Executable examples](../examples/README.md)

The `.eld` files contain source declarations and proposed implementation bodies. The experimental source pipeline parses bundled modules and uses their data declarations, but skips their function and implementation bodies during checking and execution. Supported operations use Python checker/runtime primitives or handwritten lowering; no bundled function or method currently executes its supplied `.eld` body. User-defined functions and methods, including `Cleanup` implementations, do run checked source bodies. These files are not generated canonical interfaces and do not supply all semantic metadata required by [§72](../docs/language-spec/12-interfaces-and-tooling.md#72-canonical-semantic-interfaces).

The [library profile](../docs/standard-library.md) owns representation, cost, ownership, and intrinsic contracts. Declared module identities, rather than filesystem names, define imports; there is no package manifest or additional resolution mechanism.

| Module | Initial surface | Implementation status |
| --- | --- | --- |
| [core::option](core/option.eld) | `Option`, `isSome`, `map`, `andThen` | Enum construction/matching and primitive `map`; `isSome`/`andThen` bodies are declaration-only in the interpreter |
| [core::result](core/result.eld) | `Result<E,T>`, `isOk`, `map`, `mapError`, `andThen` | Enum construction/matching, propagation, and primitive `map`; `isOk`/`mapError`/`andThen` bodies are declaration-only in the interpreter |
| [core::iter](core/iter.eld) | `Next<I,T>`, ownership-threaded `Iterator` | Trait and data declarations; source `for` uses an intrinsic finite `List` traversal |
| [core::cleanup](core/cleanup.eld) | `Cleanup<!e>` | Intrinsic protocol; user implementation bodies are checked and executed |
| [collections::linked_list](collections/linked_list.eld) | `LinkedList`, `prepend`, consuming `length`, `next` | Visible enum construction/matching; all three method bodies are declaration-only in the interpreter |
| [collections::list](collections/list.eld) | `List`, bounds errors, lookup, push, remove, replace, inspection, filter, partition, `next` | Opaque representation; primitive `new`/`length`/`remove`; remaining methods are declaration-only |
| [state::ref](state/ref.eld) | Regional `Ref`, `new`, `get`, `replace`, `set` | Cell primitives, including `set`; its supplied source body is skipped |
| [collections::dyn_array](collections/dyn_array.eld) | `DynArray`, `new`, `length`, `push`, `pop`, `withMut`, `freeze` | Mutable-owner primitives and conditional grant projection |
| [task](task.eld) | `Task`, `cancel`, `yield`, `join2` | Primitive `cancel`; `join2` expands to checked task IR through handwritten lowering, bypassing its source body; imported `task::yield` is declaration-only |

The fixture host's explicitly imported `eldude::fixture::yield` supplies the executable suspension operation used by the examples. It does not make `task::yield` executable. A declaration-only status above applies even when the file contains a body; accepting the syntax does not establish source-body checking or API support.

Callbacks used by `Option`/`Result` transformations may be skipped, so their environments must be `Discard`. They need no `Dup` guarantee because each selected callback runs once. Collection filtering/partitioning may skip and repeat their predicate, so its environment needs both permissions. `filter` additionally needs `T: Discard`; `partition` preserves all elements. Initial collection predicates are pure. These are ordinary usage rules, not new callback modes.

Capture contracts use whole arguments and environments. Mutable calls conservatively accumulate captures in surviving owners. A frozen `DynArray` may leave its allocation region only when its element type is provably capture-free; the [library profile](../docs/standard-library.md#usage-and-provenance-contracts) defines the bounds, including their application through wrappers.

The initial API omits `unwrap`, implicit cleanup, detached tasks, borrowed collection views, and effectful module initializers. Executable example coverage does not imply complete API coverage.
