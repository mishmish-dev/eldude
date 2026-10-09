# Semantic source formatter

[Documentation map](index.md) · [Formatting contract](language-spec/12-interfaces-and-tooling.md#77-formatting-and-source-stability)

## Design

The source formatter gives Eldude files deterministic layout without changing
their meaning. It uses the normative grammar's concrete syntax tree, so it can
distinguish a block from an effect row and a comparison from generic arguments.
It accepts the full ordinary source grammar, including code beyond the
experimental interpreter's subset and syntactically valid code with type errors.
It does not load imports, infer annotations, or execute the input.

The formatter preserves every non-whitespace token, including literal spelling,
parentheses, separators, duplicate effect labels, contracts, and declaration and
field order. Comments retain their text, order, and position between tokens;
trailing comments stay trailing and standalone comments stay standalone.
Re-lexing the result must reproduce the input tokens and comments. This protects
evaluation order, ownership, captures, effect-instance selection, and expression
precedence without depending on the checker's supported subset.

The existing executable AST is unsuitable for lossless printing: it drops
comments, parentheses, and literal spelling. A separate hand-written parser would
duplicate the language grammar. Instead, extend the existing grammar recognizer
to optionally retain a concrete derivation, with the recognition-only API intact.
The formatter assigns layout using grammar rules and prints the original tokens.

## Surface conventions

- Four spaces per indentation level, LF layout newlines, and one final newline.
- Nonempty declaration bodies and expression blocks expand onto separate lines.
- One statement, field, variant, match arm, or handler clause per line in a body.
- One blank line after the module header and between top-level declarations;
  consecutive imports stay together.
- Spaces around binary operators, `=`, `=>`, and after commas and colons.
- Paths, field access, generic brackets, prefix operators, and postfix operators
  remain tight; result contracts use `-> Int` or `->{Effect | e} Int`.
- Effect/capture rows and short delimited lists stay compact. Long lists break
  at their existing commas with an indented item per line; no tokens are added.
- Comments and literals are never reflowed. A long indivisible expression may
  exceed the target width of 100 columns.

Formatting is idempotent. Whitespace differences without changes to comment
placement produce the same output. This is source formatting, not the generated
semantic-interface canonicalizer: §77 explicitly allows author-written order.
Generated `semantic` blocks and inferred signature rewriting are outside this
source tool's scope.

## API and command

`src/eldude/format_eldude.py` exposes `eldude.format_eldude.format_source(text, filename='<source>') -> str`.
Syntax failures use the existing located `Diagnostic` type. Invalid syntax is
never partially formatted. The CLI accepts one file or stdin for stdout output,
and one or more explicit files with `--check` or `--write`. `--check` returns 1
for formatting differences; input/formatting errors return 2. Write mode validates
all inputs before editing any, replaces each changed file atomically, preserves
file permissions, and leaves unchanged files untouched. It refuses symlinks so
that replacement cannot silently change link identity.

## Verification

Golden cases pin readable layout for blocks, rows, operators, generics, comments,
and long lists. Corpus tests check token/comment preservation and idempotence for
all ordinary-source examples and library declarations. Positive acceptance
programs are parsed, checked, and interpreted before and after formatting against
the manifest's independent expectations, with execution events compared as well.
Existing ownership, lifetime, effect, and constraint rejection programs must
retain their intended diagnostic after formatting. CLI tests cover stdout,
stdin, checking, explicit writes, malformed input, and write safety.
