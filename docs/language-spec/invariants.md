# Appendix E — Consolidated Architectural Invariants

[Specification index](../language-specification.md)

This is an informative checklist. Each entry points to the authoritative clauses; it adds no normative requirements and does not replace their qualifications. The numbering preserves the former invariant list for review discussions.

| Invariant | Check | Authoritative clauses |
|---|---|---|
| 1 | Movability and value semantics | [§§51.1](10-host-and-ffi.md#511-movability-rule) and [74.1](12-interfaces-and-tooling.md#741-value-semantics-freedom) |
| 2 | The two fundamental usage permissions | [§§9.1](02-types-and-ownership.md#91-fundamental-predicates)–[9.2](02-types-and-ownership.md#92-usage-classes) |
| 3 | Discard has no hidden user effects | [§9.4](02-types-and-ownership.md#94-no-hidden-effect-on-discard) |
| 4 | Retained obligations and result-capture bounds | [§§13.1](04-captures-and-access.md#131-purpose), [13.4](04-captures-and-access.md#134-conservative-result-capture-bounds), and [13.6](04-captures-and-access.md#136-canonical-interfaces-and-conservative-mutation) |
| 5 | Call-scoped access and root state accounting | [§§14](04-captures-and-access.md#14-call-scoped-access) and [59.3](11-formal-semantics.md#593-access-modes) |
| 6 | Mutable-owner status and projected access | [§§9.5](02-types-and-ownership.md#95-mutable-owner-status) and [15.2](04-captures-and-access.md#152-projection-rule) |
| 7 | Aliasable cells require `CaptureFree + Discard` payload types; handles retain their region | [§§9.6](02-types-and-ownership.md#96-capture-free-types), [28.3](07-state-and-cleanup.md#283-aliasable-shared-cells)–[28.4](07-state-and-cleanup.md#284-ref-operations), and [13.5](04-captures-and-access.md#135-retention-horizons) |
| 8 | Region-state elimination | [§§27.3](07-state-and-cleanup.md#273-region-state-effect) and [61.1](11-formal-semantics.md#611-region-elimination) |
| 9 | Explicit cleanup and discharge-only control | [§§30](07-state-and-cleanup.md#30-cleanup)–[31](07-state-and-cleanup.md#31-using) |
| 10 | Handler-frame ownership and complete residual effects | [§§23.3](06-handlers.md#233-active-handler-frame-obligations), [26.5](06-handlers.md#265-residual-row), and [64.2](11-formal-semantics.md#642-lexical-handler-application) |
| 11 | The derived continuation-control envelope | [§17.3](05-effects-and-failure.md#173-derived-continuation-control-envelope) |
| 12 | Expected failure and nonrecoverable defects | [§§21.1](05-effects-and-failure.md#211-result) and [20.2](05-effects-and-failure.md#202-defect-semantics) |
| 13 | Suspension and cancellation-exit safety | [§§18.2](05-effects-and-failure.md#182-suspend) and [43.2](09-concurrency.md#432-delivery) |
| 14 | Cooperative concurrency and the parallelism boundary | [§38](09-concurrency.md#38-execution-domains-and-strands) |
| 15 | Discardable spawned results | [§40.3](09-concurrency.md#403-spawn-result-restriction) |
| 16 | Task handles versus child-lifetime ownership | [§§41.1](09-concurrency.md#411-usage) and [39.1](09-concurrency.md#391-lexical-ownership) |
| 17 | Discarding a handle leaves group ownership intact | [§41.3](09-concurrency.md#413-discarding-a-handle) |
| 18 | Taskgroup provenance and non-escape | [§§41.2](09-concurrency.md#412-taskgroup-provenance) and [67.3](11-formal-semantics.md#673-task-provenance-non-escape) |
| 19 | Lexical accounting for child effects | [§44](09-concurrency.md#44-effects-of-concurrent-children) |
| 20 | Duplicable, result-preserving inherited handlers | [§45.1](09-concurrency.md#451-group-baseline) |
| 21 | No general transfer, thread-safety, or pinning axis | [§§38.3](09-concurrency.md#383-parallelism) and [51](10-host-and-ffi.md#51-no-pinning-or-immovable-ordinary-values) |
| 22 | Foreign identity, stable storage, and temporary provenance | [§53](10-host-and-ffi.md#53-foreign-storage-and-identity) |
| 23 | Unsafe preserves ordinary static checking | [§49](10-host-and-ffi.md#49-unsafe-code) |
| 24 | Host boundaries and runnable-strand progress | [§§48](10-host-and-ffi.md#48-host-model) and [69.6](11-formal-semantics.md#696-cooperative-scheduler) |
| 25 | Complete, readable canonical semantic interfaces | [§72](12-interfaces-and-tooling.md#72-canonical-semantic-interfaces) |
| 26 | Many-shot resumption remains deferred | [§§17.2](05-effects-and-failure.md#172-resumption-modes) and [A.8](scope-and-deferrals.md#a8-deferred-or-removed-algebraic-control-variants) |
| 27 | Closed dynamic-compatibility checking | [§11.2](03-traits.md#112-dynamic-compatibility) |
| 28 | The intrinsic NonAbandoning constraint | [§17.3](05-effects-and-failure.md#173-derived-continuation-control-envelope) |
| 29 | Library combinators preserve core obligations | [§§15](04-captures-and-access.md#15-scoped-access-projection), [35.6](08-collections.md#356-ownership-preserving-early-exit-combinators), and [46.6](09-concurrency.md#466-standard-structured-concurrency-combinators) |
| 30 | Synchronous foreign-control barriers | [§56.1](10-host-and-ffi.md#561-same-domain-synchronous-callback) |
| 31 | Retained callback registration, drain, and discharge | [§§56.2](10-host-and-ffi.md#562-asynchronous-callback-from-another-native-thread)–[56.2.1](10-host-and-ffi.md#5621-lifecycle-cardinality-and-undelivered-obligations) |
| 32 | Field projection and pattern ownership | [§§8.1](02-types-and-ownership.md#81-products), [8.4](02-types-and-ownership.md#84-pattern-matching), and [21.6](05-effects-and-failure.md#216-optional-access-and-coalescing) |

In particular, [§62.2](11-formal-semantics.md#622-non-local-exit-judgment) is the common judgment for continuing control exits. Cleanup, handlers, loops, and taskgroups describe the obligations that this judgment crosses; the checklist supplies no alternative exit test.
