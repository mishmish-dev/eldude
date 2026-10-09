# Eldude

Eldude is a strict, statically typed functional language design with explicit ownership, effects, and structured concurrency. This repository contains its specification, grammar recognizer, experimental interpreter, example programs, and initial standard-library API. The interpreter implements a subset of the language.

**Start with the [documentation and project map](docs/index.md)** to find the rules, implementation files, and tests for your task. The [manifesto](docs/index.md#the-eldude-manifesto) explains the design goals.

## Quick start

The Python tools use only the standard library. Install [uv](https://docs.astral.sh/uv/getting-started/installation/); the project pins Python in [.python-version](.python-version).

Run from the repository root:

```sh
uv sync --locked
uv run python tools/run_eldude.py examples/07_source_pipeline/combined.eld
# 42
```

## Format source

The [semantic source formatter](docs/formatter.md) uses the normative grammar to
format blocks, signatures, rows, and expressions. It preserves comments, literal
spelling, contracts, and evaluation order, including code outside the interpreter's
supported subset. It does not require imports to resolve or type checking to pass.

```sh
uv run python tools/format_eldude.py examples/08_formatting/semantics.eld
uv run python tools/format_eldude.py --check path/to/file.eld
uv run python tools/format_eldude.py --write path/to/file.eld
```

Without flags it prints one formatted file to stdout; omit the filename or use `-`
to read stdin. `--check` and `--write` accept multiple files. Check mode exits 1 for
formatting differences; errors exit 2. Write mode validates all inputs before
editing, replaces changed files atomically, and refuses symlinks.

## Checks

```sh
uv run python tools/check_docs.py
uv run python tools/check_grammar.py
uv run python -m unittest discover -s tools -p 'test_*.py'
uv run python tools/run_eldude.py --examples --strict
git diff --check
```

The documentation check verifies local links and fragment anchors, chapter/code map coverage, and example tables against [manifest.json](examples/manifest.json). The grammar check verifies syntax and generated publications. The tests check static diagnostics and execution; the strict corpus run executes every positive example. See the [example guide](examples/README.md) for expected values and rejection fixtures.

After editing [eldude.ebnf](docs/eldude.ebnf) or the originating parsing/interface clauses, regenerate the Markdown and JSON grammar publications with `uv run python tools/check_grammar.py --write`. The [editing guide](docs/index.md#editing-and-checking) identifies the source files.

## Source-to-execution experiment

The [implementation guide](tools/README.md#source-to-execution-experiment) describes supported source forms, entry-point conventions, diagnostics, and remaining limits. The [file map](tools/README.md#file-map) connects each compiler component to its tests. Resources are simulated; execution uses a bounded cooperative scheduler.

## Inference experiment

The [inference guide](tools/README.md#inference-experiment) covers annotated expression checking, effect rows, ownership, captures, and its conservative boundaries.

## Handler and resumption experiment

The [handler guide](tools/README.md#handler-and-resumption-experiment) covers clause checking, explicit evidence, resumption, forwarding, and the interpreter API.
