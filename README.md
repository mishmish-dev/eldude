# Eldude

Eldude is a strict, statically typed functional language design with explicit ownership, effects, and structured concurrency. This repository contains its specification, grammar recognizer, [experimental Python interpreter](python-impl/src/eldude/), [example programs](eldude-program-examples/README.md), and [initial standard-library API](eldude-stdlib/README.md). The interpreter implements a subset of the language.

**Start with the [documentation and project map](docs/index.md)** to find the rules, implementation files, and tests for your task. The [manifesto](docs/index.md#the-eldude-manifesto) explains the design goals.

## Quick start

The Python implementation uses only the standard library at runtime. Install [uv](https://docs.astral.sh/uv/getting-started/installation/); the project pins Python in [.python-version](.python-version).

Run from the repository root:

```sh
uv sync --locked
uv run eldude test
# 133 tests executed; 0 failed
uv run eldude run --app source_pipeline_combined
```

`run` reports the application name and its exit status on stderr. The example
applications call `verify()`, which checks the expected result and exits with
status `0` when it matches. To print an example's `main()` result instead, use
`uv run eldude-run eldude-program-examples/src/04_effects/handler.eld` (prints `42`).

## Project CLI

The installed `eldude` command provides the project workflow from
[the tooling design](docs/tooling-design.md). `uv sync` installs the package from
`python-impl/src/eldude/` and its commands into the pinned Python environment:

```sh
uv run eldude --help
uv run eldude new /tmp/hello --lib
uv run eldude check --manifest-path /tmp/hello/eldude.toml
uv run eldude fmt --manifest-path /tmp/hello/eldude.toml
uv run eldude metadata --manifest-path /tmp/hello/eldude.toml
uv run eldude check eldude-program-examples/src/09_tooling/application.eld
```

Commands discover the nearest `eldude.toml`, or accept `--manifest-path`.
The repository's [eldude.toml](eldude.toml) uses `eldude-program-examples/src` as its source root
and registers every positive program as an application and isolated result-checking
test; `eldude test` runs them all from the repository root.
Workspaces support `--package NAME` and `--workspace`, share a root lockfile, and
reject member toolchain overrides. Path dependencies are resolved by declared
package/module identities; transitive and test-only imports do not leak into
production modules. `lock` and `update` reconcile the path graph. Ordinary `check`,
`build`, `run`, and `test` reuse or update `eldude.lock` as needed. `--locked` is
optional for CI or verification: it fails if the lock is missing or stale instead
of changing it. `--offline` is accepted independently;
this path-only implementation never fetches remote sources.

`check` checks ordinary libraries without a `main` and never executes initializers.
Bare checking includes source and test modules; `--app`, `--embed`, or `--test`
selects a root's import closure. `check FILE.eld` checks an ordinary module without
host conformance. `metadata` reads local project state without creating a lock or
requiring the pin to match. `clean` removes only the owning project's `build/`.

### Experimental Python builds

`build`, `run`, and isolated executable tests support an explicit
`python::experimental` host. For example:

```toml
manifest-version = 1

[package]
name = "hello"
version = "0.1.0"
host = "python::experimental"

[[app]]
name = "hello"
entry = "hello::main"
```

With `src/main.eld` declaring `module hello; pub fn main() -> Int { 0 }`:

```sh
uv run eldude build --manifest-path /tmp/hello/eldude.toml
uv run eldude run --manifest-path /tmp/hello/eldude.toml
uv run eldude test --manifest-path /tmp/hello/eldude.toml --message-format=json
```

`package.host` supplies the host for apps and tests that omit `host`; a target's
explicit `host` overrides it. Apps and tests must have either a package host or
their own host. Embedding targets require their own explicit `host`.

The Python host requires an exported, nongeneric, nullary `Int` function, closed
handler evidence, and a result from 0 through 255. That result becomes the process
exit status; other results and execution defects fail. Register tests with
`[[test]]`, `name`, and `entry` using the same convention; `host` may be inherited
from the package. Each runner starts in its package directory in a separate Python
process. No registered runners
reports `No test targets selected` with zero executed tests.

Application artifacts are `.pyz` archives containing checked IR and the interpreter;
they execute without rereading source or recompiling. Libraries produce experimental
`.eldir.json` products. Paths are reported by builds, metadata, and JSON events under
`build/<machine-target>/<dev-or-release>/`. `--release` records a distinct profile
but currently uses the same interpreter. Immutable application artifact names prevent
concurrent builds from launching one another's output; a failed rebuild never runs
an old artifact.

`new` and `init` preserve the design's `cli::standard` application template. That
production host is not implemented: explicitly change its manifest host to
`python::experimental` to run with Python. Native builds, embeddings, cross targets,
an Eldude application-argument API, registry/Git resolution, complete canonical
interfaces, and semantic incremental caching remain unsupported. Checking still
checks imported source closures, and resources/I/O retain the fixture limitations.
See the [implementation guide](docs/implementation.md#project-tooling) for boundaries.

## Format source

The [semantic source formatter](docs/formatter.md) uses the normative grammar to
format blocks, signatures, rows, and expressions. It preserves comments, literal
spelling, contracts, and evaluation order, including code outside the interpreter's
supported subset. It does not require imports to resolve or type checking to pass.

```sh
uv run eldude-format eldude-program-examples/src/08_formatting/semantics.eld
uv run eldude-format --check path/to/file.eld
uv run eldude-format --write path/to/file.eld
```

Without flags it prints one formatted file to stdout; omit the filename or use `-`
to read stdin. `--check` and `--write` accept multiple files. Check mode exits 1 for
formatting differences; errors exit 2. Write mode validates all inputs before
editing, replaces changed files atomically, and refuses symlinks.

The project CLI reuses this formatter: `eldude fmt` writes the selected packages'
source/test files, `fmt --check` checks them, and `fmt --diff` prints changes without
writing. Explicit files/directories and sole stdin input `fmt -` also work without
a manifest. No-argument formatting requires a project. All selected inputs and
toolchain pins are validated before writing; each replacement preserves permissions
and checks for concurrent edits. The standalone `eldude-format` command keeps its stdout default.

## Checks

These maintenance commands and `eldude-run --examples` require a repository
checkout. Installed wheels include the grammar and standard library for running,
checking, formatting, and building user programs.

```sh
uv run python -m eldude.tooling.check_docs
uv run python -m eldude.source.grammar
uv run python -m unittest discover -s python-impl/tests -p 'test_*.py'
uv run eldude test
uv run eldude-run --examples --strict
git diff --check
```

The documentation check verifies local links and fragment anchors, chapter/code map coverage, and example tables against [manifest.json](eldude-program-examples/manifest.json). The grammar check verifies syntax and generated publications. The tests check static diagnostics and execution; the strict corpus run executes every positive example. See the [example guide](eldude-program-examples/README.md) for expected values and rejection fixtures.

After editing [eldude.ebnf](docs/eldude.ebnf) or the originating parsing/interface clauses, regenerate the Markdown and JSON grammar publications with `uv run python -m eldude.source.grammar --write`. The [editing guide](docs/index.md#editing-and-checking) identifies the source files.

## Source-to-execution experiment

The [implementation guide](docs/implementation.md#source-to-execution-experiment) describes supported source forms, entry-point conventions, diagnostics, and remaining limits. The [file map](docs/implementation.md#file-map) connects each compiler component to its tests. Resources are simulated; execution uses a bounded cooperative scheduler.

## Inference experiment

The [inference guide](docs/implementation.md#inference-experiment) covers annotated expression checking, effect rows, ownership, captures, and its conservative boundaries.

## Handler and resumption experiment

The [handler guide](docs/implementation.md#handler-and-resumption-experiment) covers clause checking, explicit evidence, resumption, forwarding, and the interpreter API.

## Licence

> THE LICENCE
> Version 1.0
> 
> Copyright (c) 2026 Mishmish Dev
> 
> Right. We’ll do this with an example. There’s you, and there’s another chap. He isn’t here. I’ve invented him. We don’t need to look for him.
> 
> You’ve obtained a copy of some software, together with the documents that go with it. For the purposes of this explanation, all of that is “the Software”. I’m going to point at this bit of paper when I say it. It isn’t actually on the paper. That’s just to help.
> 
> Now, you’re given permission, at no cost, to deal with the Software without restriction. You can use it, copy it, modify it, merge it, publish it, distribute it, sublicense it, or sell copies. Any of those. Other things as well. We haven’t made a list of everything because then we’d still be making the list.
> 
> So you give a copy to this other chap. He’s got it now. You’ve still got it as well. That’s perfectly normal. We haven’t accidentally given it to you twice.
> 
> You’re allowed to let him do all those things too. And that applies to anyone you supply it to. He could be several people. He couldn’t personally be several people, but there could be several people in the position I’ve put him in.
> 
> There is a condition: every copy, or substantial portion of the Software, must include the copyright notice above and this permission notice. Those go with it. So when he gets it, he gets the bit explaining why he’s allowed to have it and what he’s allowed to do. Otherwise I’d have to explain this to him separately, and we’ve only just got you sorted.
> 
> Now, the Software is supplied “as is”, without any warranty, express or implied. No promises about merchantable quality, suitability for a particular purpose, or noninfringement of anyone else’s rights. It might do exactly what you want. That’s allowed to happen. They just haven’t promised it will.
> 
> And under no circumstances are the authors or copyright holders liable for any claims, damages or other liability arising from or connected with the Software, using it, or any other dealings with it. Contract, tort, otherwise—it covers all of those.
> 
> So if the chap has a claim connected with it, the authors and copyright holders aren’t liable. You might be an author as well, of course. I haven’t asked. You could be giving him something you wrote yourself.
> 
> In which case I’ve been imagining an extra person unnecessarily.
> 
> Right. Where’s this other chap, then? I’d like to hear his side.
