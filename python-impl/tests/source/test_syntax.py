"""Located subset parsing, with the normative grammar as the syntax boundary."""
import unittest

from eldude.source.grammar import GRAMMAR, Grammar


class SourceSyntaxTests(unittest.TestCase):
    def test_positioned_lexer_can_retain_comments_without_parsing_literal_text(self):
        grammar = Grammar(GRAMMAR.read_text(encoding='utf-8'))
        source = '// header\r\nmodule m; /* gap */ let x="// not a comment";'
        tokens = grammar.lex_spanned(source, comments=True)
        self.assertEqual([t.value for t in tokens if t.kind.endswith('_COMMENT')],
                         ['// header', '/* gap */'])
        self.assertEqual([(t.kind, t.value) for t in tokens if not t.kind.endswith('_COMMENT')],
                         grammar.lex(source, 'source_file'))
        self.assertTrue(all(source[t.start:t.end] == t.value for t in tokens))

    def test_positioned_lexer_preserves_legacy_tokens(self):
        grammar = Grammar(GRAMMAR.read_text(encoding='utf-8'))
        text = '// trivia\nmodule m; /* gap */\npub fn main()->Int { 42 }'
        self.assertTrue(hasattr(grammar, 'lex_spanned'), 'positioned lexing is missing')
        tokens = grammar.lex_spanned(text, 'source_file')
        self.assertEqual([(t.kind, t.value) for t in tokens], grammar.lex(text, 'source_file'))
        self.assertEqual(text[tokens[-2].start:tokens[-2].end], '42')
        self.assertEqual(tokens[0].start, 10)

    def test_ast_retains_filename_and_exact_span(self):
        from eldude.source.syntax import parse_source
        ast = parse_source('module m;\npub fn main()->Int { 42 }', 'literal.eld')
        self.assertEqual(ast.kind, 'module')
        function = ast.items[1][0]
        literal = function.items[-1].items[1]
        self.assertEqual((literal.kind, literal.items), ('int', (42,)))
        self.assertEqual((literal.span.filename, literal.span.line, literal.span.column),
                         ('literal.eld', 2, 22))

    def test_syntax_and_unsupported_are_distinct(self):
        from eldude.source.syntax import Diagnostic, parse_source
        for source, code, column in (
            ('module m; fn f()->Int { 1 2 }', 'syntax', 27),
            ('module m; fn f()->Int { 1.0 }', 'unsupported', 25),
            ('module m; fn f()->Int { 1 + }', 'syntax', 29),
        ):
            with self.subTest(source=source), self.assertRaises(Diagnostic) as caught:
                parse_source(source, 'bad.eld')
            self.assertEqual(caught.exception.code, code)
            self.assertEqual(caught.exception.span.column, column)

    def test_lexical_failure_and_missing_delimiter_have_locations(self):
        from eldude.source.syntax import Diagnostic, parse_source
        for source, line, column in (
            ('module m;\n$', 2, 1),
            ('module m;\npub fn main()->Int {', 2, 21),
            ('module m;\nlet x="\\u{d800}";', 2, 8),
        ):
            with self.subTest(source=source), self.assertRaises(Diagnostic) as caught:
                parse_source(source, 'syntax.eld')
            self.assertEqual(caught.exception.code, 'syntax')
            self.assertEqual((caught.exception.span.line, caught.exception.span.column), (line, column))

    def test_nested_numeric_operators_parse_without_folding_away_overflow(self):
        from eldude.source.syntax import parse_source
        ast = parse_source('module m; pub fn main()->Int { -(-9223372036854775808) }')
        expression = ast.items[1][0].items[-1].items[1]
        self.assertEqual(expression.kind, 'unary')
        self.assertEqual(expression.items[1].items, (-9223372036854775808,))


if __name__ == '__main__':
    unittest.main()
