# Appendix D — Evaluation Criteria for an Implementation

[Specification index](../language-specification.md)

Eldude's design claims are semantic goals, not implementation-performance results.

A compiler/runtime SHOULD publish measurements for:

- clean build time;
- private-body incremental edit latency;
- public-interface edit latency;
- time to first diagnostic;
- peak compiler memory;
- generic code size;
- handler cost by resumption mode;
- non-divergence-analysis cost;
- capture/usage-checking cost;
- `List` copy-on-write/reuse behavior;
- linear collection traversal cost;
- region mutation overhead;
- task spawn/await/cancellation overhead;
- taskgroup shutdown latency;
- FFI transition and callback-posting cost;
- interface hash stability and incremental cache hit rate.

Claims relative to Haskell, Koka, Rust, OCaml, Roc, or other languages require measured evidence on stated workloads and toolchain versions.
