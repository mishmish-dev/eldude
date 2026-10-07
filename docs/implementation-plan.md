# Executable example coverage

**Status: completed milestone.** Current behavior and limits live in the [implementation guide](../tools/README.md); the [example guide](../examples/README.md) records coverage and expected outcomes. This page preserves the scope of the completed work.

The milestone made all 49 positive examples executable through located parsing, static checking, and interpretation, preserving their source, expected results, diagnostics, handler evidence, ownership checks, and fixture traces. It reused the expression IR and interpreter, kept the normative grammar unchanged, and used only the Python standard library.

The five completed areas were:

1. Located syntax for data declarations, patterns, access modes, generics, regions, traits, control flow, and tasks.
2. Data/control checking and execution: exhaustive matching, linear destructuring, recursion, ordered startup, and `Result`/`Option` flow.
3. Module identity resolution, traits and methods, collection/cell primitives, and region/capture provenance.
4. Structured cooperative tasks, consuming await/cancel, handler inheritance, and library join.
5. Manifest coverage and regressions for ownership, cleanup, declarations, data, recursion, and tasks.

Use the [repository checks](../README.md#checks) to verify the milestone remains covered. Passing this corpus does not imply complete language or library conformance.
