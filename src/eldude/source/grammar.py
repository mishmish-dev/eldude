"""Check Eldude EBNF and its Markdown/JSON publications; recognize syntax only."""
import argparse
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GRAMMAR = Path(__file__).resolve().parents[1] / 'eldude.ebnf'
if not GRAMMAR.exists():
    GRAMMAR = ROOT / 'docs/eldude.ebnf'
FOUNDATIONS = ROOT / 'docs/language-spec/01-foundations.md'
INTERFACES = ROOT / 'docs/language-spec/12-interfaces-and-tooling.md'
FORMAL = ROOT / 'docs/formal-grammar.md'
MACHINE = ROOT / 'docs/eldude-grammar.json'
BEGIN = '<!-- BEGIN GENERATED ELDUDE GRAMMAR -->'
END = '<!-- END GENERATED ELDUDE GRAMMAR -->'
META = re.compile(r'\s*(::=|"(?:[^"\\]|\\.)*"|[A-Za-z_][A-Za-z_0-9]*|[;|()?*+])')


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    start: int
    end: int


@dataclass(frozen=True)
class SyntaxNode:
    name: str
    start: int
    end: int
    children: tuple


class LexError(ValueError):
    def __init__(self, message, offset):
        super().__init__(message)
        self.offset = offset


class Grammar:
    def __init__(self, text):
        self.rules = {}
        self.patterns = {}
        self.skips = {}
        self.keywords = set()
        body = []
        for line in text.splitlines():
            if line.lstrip().startswith('#') or not line.strip():
                continue
            if line.startswith('%keywords '):
                self.keywords.update(json.loads(line[len('%keywords '):-1]).split())
            elif line.startswith(('%token ', '%skip ')):
                kind, name, pattern = re.fullmatch(r'%(token|skip) (\w+) = (".*");', line).groups()
                regex = re.compile(json.loads(pattern))
                if regex.match(''):
                    raise ValueError(f'Empty lexical rule: {name}')
                if kind == 'skip':
                    if name in self.skips:
                        raise ValueError(f'Duplicate skip rule: {name}')
                    self.skips[name] = regex
                else:
                    if name in self.patterns:
                        raise ValueError(f'Duplicate token: {name}')
                    self.patterns[name] = regex
            else:
                body.append(line)
        body = '\n'.join(body)
        tokens = []
        pos = 0
        while body[pos:].strip():
            match = META.match(body, pos)
            if not match:
                raise ValueError(f'Invalid EBNF near {body[pos:pos+30]!r}')
            tokens.append(match[1])
            pos = match.end()
        self.tokens, self.pos = tokens, 0
        while self.pos < len(tokens):
            name = self.take()
            if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', name):
                raise ValueError(f'Invalid production name: {name}')
            self.take('::=')
            ast = self.choice()
            self.take(';')
            if name in self.rules or name in self.patterns:
                raise ValueError(f'Duplicate production: {name}')
            self.rules[name] = ast
        known = set(self.rules) | set(self.patterns)
        for name, ast in self.rules.items():
            missing = self.references(ast) - known
            if missing:
                raise ValueError(f'{name}: undefined symbols {sorted(missing)}')
        literal_words = set()
        def collect_literals(ast):
            kind, value = ast
            if kind == 'literal':
                literal_words.add(value)
            elif kind in ('choice', 'sequence'):
                for item in value:
                    collect_literals(item)
            elif kind != 'name':
                collect_literals(value)
        for ast in self.rules.values():
            collect_literals(ast)
        if self.keywords - literal_words:
            raise ValueError(f'Reserved syntax has no production: {sorted(self.keywords - literal_words)}')
        self.bnf = {}
        self.serial = 0
        for name, ast in self.rules.items():
            self.bnf[name] = self.expand(ast)

    def take(self, expected=None):
        if self.pos >= len(self.tokens):
            raise ValueError('Unexpected end of EBNF')
        value = self.tokens[self.pos]
        if expected is not None and value != expected:
            raise ValueError(f'Expected {expected}, got {value}')
        self.pos += 1
        return value

    def choice(self):
        alternatives = [self.sequence()]
        while self.pos < len(self.tokens) and self.tokens[self.pos] == '|':
            self.take('|')
            alternatives.append(self.sequence())
        return ('choice', alternatives)

    def sequence(self):
        terms = []
        while self.pos < len(self.tokens) and self.tokens[self.pos] not in ('|', ')', ';'):
            value = self.take()
            if value == '(':
                node = self.choice()
                self.take(')')
            elif value.startswith('"'):
                node = ('literal', json.loads(value))
            elif re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', value):
                node = ('name', value)
            else:
                raise ValueError(f'Unexpected EBNF term: {value}')
            if self.pos < len(self.tokens) and self.tokens[self.pos] in ('?', '*', '+'):
                node = (self.take(), node)
            terms.append(node)
        return ('sequence', terms)

    def references(self, ast):
        kind, value = ast
        if kind == 'name':
            return {value}
        if kind == 'literal':
            return set()
        if kind in ('choice', 'sequence'):
            return set().union(*(self.references(x) for x in value))
        return self.references(value)

    def expand(self, ast):
        kind, value = ast
        if kind == 'name':
            return [(('token', value) if value in self.patterns else value,)]
        if kind == 'literal':
            return [(('literal', value),)]
        if kind == 'choice':
            return [rhs for item in value for rhs in self.expand(item)]
        if kind == 'sequence':
            result = [()]
            for item in value:
                result = [a+b for a in result for b in self.expand(item)]
            return result
        self.serial += 1
        helper = f'@{self.serial}'
        options = self.expand(value)
        if kind == '?':
            self.bnf[helper] = [()] + options
        elif kind == '*':
            self.bnf[helper] = [()] + [rhs+(helper,) for rhs in options]
        else:
            self.bnf[helper] = options + [rhs+(helper,) for rhs in options]
        return [(helper,)]

    def literals(self, start):
        pending, visited, literals = [start], set(), set()
        while pending:
            rule = pending.pop()
            if rule in visited:
                continue
            visited.add(rule)
            for rhs in self.bnf[rule]:
                for symbol in rhs:
                    if isinstance(symbol, str):
                        pending.append(symbol)
                    elif symbol[0] == 'literal':
                        literals.add(symbol[1])
        return sorted(literals)

    def vocabulary(self, start):
        return sorted((s for s in self.literals(start) if not re.fullmatch(r'\w+', s)), key=lambda s: (-len(s), s))

    def machine_format(self):
        return {
            'format': 'eldude-grammar',
            'format_version': 1,
            'language': {'name': 'Eldude'},
            'entry_points': {'source': 'source_file', 'interface': 'interface_file'},
            'lexical': {
                'encoding': 'UTF-8',
                'regex_dialect': 'Python re',
                'matching': 'longest; ties prefer tokens in declaration order before punctuation',
                'tokens': [{'name': name, 'pattern': regex.pattern} for name, regex in self.patterns.items()],
                'skip': [{'name': name, 'pattern': regex.pattern} for name, regex in self.skips.items()],
                'reserved_words': sorted(self.keywords),
                'contextual_words': sorted(s for s in self.literals('source_file') if re.fullmatch(r'[A-Za-z]+', s) and s not in self.keywords),
                'literal_vocabulary': {entry: self.literals(entry) for entry in ('source_file', 'interface_file')},
                'unicode_scalar_range': [0, 0x10FFFF],
                'excluded_scalar_ranges': [[0xD800, 0xDFFF]],
            },
            'productions': {
                name: [[{'rule': symbol} if isinstance(symbol, str) else {symbol[0]: symbol[1]} for symbol in rhs] for rhs in alternatives]
                for name, alternatives in self.bnf.items()
            },
        }

    def lex(self, text, start):
        """Legacy token-pair API, also used by exported-grammar consumers."""
        return [(t.kind, t.value) for t in self.lex_spanned(text, start)]

    def lex_spanned(self, text, start='source_file', *, comments=False):
        punctuation = self.vocabulary(start)
        result, pos = [], 0
        while pos < len(text):
            skipped = next(((name, m) for name, regex in self.skips.items()
                            if (m := regex.match(text, pos))), None)
            if skipped:
                name, match = skipped
                if comments and name != 'SPACE':
                    result.append(Token(name, match[0], pos, match.end()))
                pos = match.end()
                continue
            candidates = [(len(m[0]), name, m[0]) for name, regex in self.patterns.items()
                          if (m := regex.match(text, pos))]
            candidates += [(len(s), 'PUNCT', s) for s in punctuation if text.startswith(s, pos)]
            if not candidates:
                raise LexError(f'Invalid source token: {text[pos:pos+20]!r}', pos)
            _, kind, value = max(candidates, key=lambda item: item[0])
            if kind == 'IDENT' and value in self.keywords:
                kind = 'KEYWORD'
            if kind in ('STRING_LITERAL', 'CHAR_LITERAL'):
                if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
                    raise LexError('Surrogate scalar in literal', pos)
                for escape in re.finditer(r"\\(?:[\"'\\nrt0]|u\{[0-9a-fA-F]{1,6}\})", value):
                    if escape[0].startswith('\\u{'):
                        scalar = int(escape[0][3:-1], 16)
                        if scalar > 0x10FFFF or 0xD800 <= scalar <= 0xDFFF:
                            raise LexError('Invalid Unicode scalar escape', pos + escape.start())
            result.append(Token(kind, value, pos, pos + len(value)))
            pos += len(value)
        return result

    def accepts(self, text, start='source_file'):
        if start not in self.bnf:
            raise ValueError(f'Unknown grammar entry point: {start}')
        try:
            tokens = self.lex(text, start)
        except ValueError:
            return False
        return self.syntax_failure(tokens, start) is None

    def syntax_failure(self, tokens, start='source_file'):
        """Recognize token pairs; return the failing token index, or None."""
        return self._recognize(tokens, start, False)[1]

    def parse_tokens(self, tokens, start='source_file'):
        """Return (concrete tree, failure index) for token pairs, with one None.

        Children are named-rule nodes or indexes into tokens. EBNF repetition
        helpers are flattened; declaration order breaks ambiguous derivation ties.
        """
        return self._recognize(tokens, start, True)

    def _recognize(self, tokens, start, build_tree):
        if start not in self.bnf:
            raise ValueError(f'Unknown grammar entry point: {start}')
        chart = [{} for _ in range(len(tokens)+1)]
        initial = ('@start', (start,), 0, 0)
        chart[0][initial] = ()
        for index in range(len(chart)):
            changed = True
            while changed:
                before = len(chart[index])
                for (lhs, rhs, dot, origin), children in tuple(chart[index].items()):
                    if dot == len(rhs):
                        completed = ()
                        if build_tree:
                            completed = children if lhs.startswith('@') else (SyntaxNode(lhs, origin, index, children),)
                        for (outer_lhs, outer_rhs, outer_dot, outer_origin), prefix in tuple(chart[origin].items()):
                            if outer_dot < len(outer_rhs) and outer_rhs[outer_dot] == lhs:
                                chart[index].setdefault((outer_lhs, outer_rhs, outer_dot+1, outer_origin),
                                                        prefix + completed)
                    else:
                        symbol = rhs[dot]
                        if isinstance(symbol, str):
                            for option in self.bnf[symbol]:
                                chart[index].setdefault((symbol, option, 0, index), ())
                        elif index < len(tokens):
                            kind, value = tokens[index]
                            if (symbol[0] == 'token' and kind == symbol[1]) or (symbol[0] == 'literal' and value == symbol[1]):
                                chart[index+1].setdefault((lhs, rhs, dot+1, origin),
                                                          children + (index,) if build_tree else ())
                changed = len(chart[index]) != before
        if ('@start', (start,), 1, 0) in chart[-1]:
            tree = chart[-1][('@start', (start,), 1, 0)][0] if build_tree else None
            return tree, None
        return None, max(i for i, states in enumerate(chart) if states)

def section(source, number):
    spec = source.read_text(encoding='utf-8')
    heading = re.search(r'^#{2,3} '+re.escape(number)+r'\.? [^\n]+\n', spec, re.M)
    if heading is None:
        raise ValueError(f'Missing specification section: {number}')
    body = spec[heading.end():]
    next_heading = re.search(r'^#{1,3} ', body, re.M)
    body = body[:next_heading.start() if next_heading else len(body)].strip()

    def publication_link(match):
        target = match[0]
        if re.match(r'[A-Za-z][A-Za-z0-9+.-]*:|//', target):
            return target
        name, separator, anchor = target.partition('#')
        original = source.parent / name if name else source
        return Path(os.path.relpath(original, FORMAL.parent)).as_posix() + separator + anchor

    return re.sub(r'(?<=\]\()[^)\n]+(?=\))', publication_link, body)

def formal_markdown(text):
    return '''# Eldude Formal Grammar

**Status:** normative syntax with an implemented recognizer; source execution covers a subset.

This complete grammar covers ordinary Eldude source and generated canonical semantic interfaces. It is generated from [eldude.ebnf](eldude.ebnf), the parsing clauses in [Foundations and programs](language-spec/01-foundations.md), and the interface clauses in [Interfaces, compilation, and tooling](language-spec/12-interfaces-and-tooling.md). Numbered references retain their identifiers in the [language specification](language-specification.md). The [manifesto](index.md#the-eldude-manifesto) describes the design principles.

The machine-readable forms are the EBNF artifact and [eldude-grammar.json](eldude-grammar.json), which contains normalized BNF, lexical rules, and parsing conventions. Syntax acceptance does not establish typing, visibility, usage, effects, termination, exhaustiveness, or audited native validity. Those judgments remain in the language specification.

## Entry points and notation

`source_file` parses an ordinary file, beginning with exactly one `module path;` declaration. `interface_file` parses generated canonical interfaces and additionally permits `semantic` blocks. The interface-only productions are unreachable from `source_file`; generated native contracts are not source annotations.

In EBNF, `::=` defines a production, `|` selects an alternative, parentheses group, `?` means zero or one, `*` means zero or more, and `+` means one or more. A sequence matches left to right. JSON strings quote exact terminals and regular expressions. Unquoted names reference productions or lexical token categories. An empty sequence matches no tokens. `#` starts a whole-line artifact comment.

`%token NAME = "regex";` defines a lexical category, `%skip NAME = "regex";` defines trivia, and `%keywords "words";` excludes reserved words from `IDENT`. Regexes use Python's `re` syntax without additional flags. Skip rules are considered in declaration order before token recognition. Otherwise choose the longest lexical match; ties prefer token categories in declaration order before punctuation. Reserved identifier lexemes become keyword tokens. Literal productions match exact spelling; lexical-category productions match category. Punctuation comes from the selected entry point's reachable literal vocabulary, so interface-only compound words do not alter ordinary source lexing. There is no implicit end-of-file token: the selected entry point must consume the entire token stream.

## Reserved words, sigils, and tokens

'''+section(FOUNDATIONS, '2.6')+'''

## Lexical payloads and source forms

'''+section(FOUNDATIONS, '2.9')+'''

## Operators and precedence

'''+section(FOUNDATIONS, '2.7')+'''

## Parsing and derivation selection

'''+section(FOUNDATIONS, '2.8')+'''

These rules select association among grammar derivations using syntax alone. The conformance recognizer checks token-stream membership and does not construct an AST or perform derivation selection; compiler parsers must also implement the stated association rules.

## Complete lexical and syntactic grammar

'''+BEGIN+'\n```ebnf\n'+text.rstrip()+'\n```\n'+END+'''

## Generated semantic clauses

'''+section(INTERFACES, '72.7')+'''

## Generated native contracts

'''+section(INTERFACES, '72.9')+'''

## Canonical interface ordering

'''+section(INTERFACES, '77')+'''

## JSON representation

`eldude-grammar.json` uses format `eldude-grammar`; `format_version` identifies the JSON schema version. `entry_points` names the ordinary source and generated interface starts. `lexical.tokens` and `lexical.skip` are ordered arrays of `{ "name": ..., "pattern": ... }`; array order retains lexical priority. `reserved_words` and `contextual_words` expose the word categories. `literal_vocabulary` lists the reachable literals for each entry point. String/character token recognition additionally validates the Unicode scalar range and excluded surrogate interval recorded in `lexical`.

`productions` maps each nonterminal to an array of alternatives. Each alternative is an ordered array of symbols; `[]` means epsilon. A symbol has exactly one key: `rule` references a nonterminal, `token` references a lexical category, and `literal` matches exact spelling. Names beginning with `@` are generated repetition helpers, not Eldude source tokens. This representation expands EBNF options and repetitions into ordinary BNF. `parsing_conventions` preserves the normative derivation/association rules above; consumers must apply them when building syntax trees.

## Regeneration and verification

From the repository root:

```sh
uv run python -m eldude.source.grammar --write
uv run python -m eldude.source.grammar
uv run python -m unittest discover -s tests -p 'test_grammar*.py'
```

The first command regenerates this document and the JSON export; the specification chapters are inputs and are not rewritten. The second rejects undefined symbols, duplicate productions, malformed EBNF, reserved-word drift, or stale generated publications. Tests cover accepted/rejected syntax, source/interface separation, JSON consumption, and stale-publication detection. Edit the EBNF or originating specification clauses, then regenerate; do not edit generated presentations directly.
'''

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='Refresh standalone grammar Markdown and JSON')
    args = parser.parse_args()
    text = GRAMMAR.read_text(encoding='utf-8')
    grammar = Grammar(text)
    for entry in ('source_file', 'interface_file'):
        grammar.vocabulary(entry)
    keyword_section = section(FOUNDATIONS, '2.6').split('```text\n', 1)[1].split('```', 1)[0]
    if set(keyword_section.split()) != grammar.keywords:
        raise SystemExit('Reserved words differ between §2.6 and the lexical grammar')
    machine = grammar.machine_format()
    machine['parsing_conventions'] = [line[2:] for line in section(FOUNDATIONS, '2.8').splitlines() if line.startswith('- ')]
    publications = {
        FORMAL: formal_markdown(text),
        MACHINE: json.dumps(machine, indent=2, sort_keys=True, ensure_ascii=False)+'\n',
    }
    for path, expected in publications.items():
        if args.write:
            path.write_text(expected, encoding='utf-8', newline='\n')
        elif not path.exists() or path.read_text(encoding='utf-8') != expected:
            raise SystemExit(f'{path.name} is stale; run uv run python -m eldude.source.grammar --write')
    print(f'Grammar checked: {len(grammar.rules)} productions, all symbols defined; formal Markdown and JSON synchronized')

if __name__ == '__main__':
    main()
