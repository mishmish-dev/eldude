# Executable example coverage

The requested result is all 49 positive examples running unchanged through located parsing, static checking and execution. Preserve existing diagnostics, handler evidence, ownership checking, and fixture traces. The normative language specification and standard-library declarations define behavior; do not alter examples to make them pass.

Use the existing expression IR and interpreter. Extend parsing without changing the normative grammar. Add focused modules only where a separate responsibility makes the existing compiler easier to maintain. Python standard library only.

1. Extend the located AST for enums/patterns, declaration initialization, access modes, generic/region types, traits/impls, propagation/returns, iteration, and tasks. Parse the positive examples and bundled library source; preserve old AST shapes where possible.
2. Extend data/control checking and execution: nominal variants, exhaustive matching, linear destructuring, Nat, recursive function bindings with termination/effect validation, ordered startup, and Result/Option control flow.
3. Resolve source modules by declared identity. Check trait implementations and associated types; execute source methods and provide explicit implementations for the bundled opaque List, Ref and DynArray primitive contracts. Preserve region/capture bounds and mutable-owner provenance.
4. Add structured cooperative tasks, taskgroup lifetime, spawn/await, inherited handler checks, child-local handlers, and library join. Keep scheduler state inside each execution.
5. Move every newly supported example from pending to runnable, preserve independently specified expected values, add semantic counterexamples, run the full suite and strict corpus command, and update documentation.

Validation: `python -m unittest discover -s tools -p 'test_*.py'`, `python tools/check_grammar.py`, `python tools/run_eldude.py --examples --strict`, and `git diff --check`. Review interactions between branch/early exits and cleanup, recursive calls and admitted effects, imported identities and aliases, region escape through aggregate/call results, and task handler inheritance.

Work in the current checkout so the previous uncommitted implementation remains available. Parser work is isolated to source_syntax.py; compiler/checker integration remains with the primary agent. Independent runtime helpers and their tests may be delegated with explicit interfaces. Do not commit or publish changes as part of this task.

Implemented: all five phases above. All 49 positive examples retain their original source/results and are marked runnable. Regression coverage includes static ownership/capture failures, declaration startup, nominal and generic data, recursion, cleanup, and task inheritance. Remaining profile limits are documented in the root README; existential trait objects and multiple specialized method implementations remain explicit limits.
