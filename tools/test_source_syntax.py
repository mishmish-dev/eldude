"""Located subset parsing, with the normative grammar as the syntax boundary."""
import unittest

from check_grammar import GRAMMAR, Grammar


class SourceSyntaxTests(unittest.TestCase):
    def test_positioned_lexer_preserves_legacy_tokens(self):
        grammar = Grammar(GRAMMAR.read_text(encoding='utf-8'))
        text = '// trivia\nmodule m; /* gap */\npub fn main()->Int { 42 }'
        self.assertTrue(hasattr(grammar, 'lex_spanned'), 'positioned lexing is missing')
        tokens = grammar.lex_spanned(text, 'source_file')
        self.assertEqual([(t.kind, t.value) for t in tokens], grammar.lex(text, 'source_file'))
        self.assertEqual(text[tokens[-2].start:tokens[-2].end], '42')
        self.assertEqual(tokens[0].start, 10)

    def test_ast_retains_filename_and_exact_span(self):
        from source_syntax import parse_source
        ast = parse_source('module m;\npub fn main()->Int { 42 }', 'literal.eld')
        self.assertEqual(ast.kind, 'module')
        function = ast.items[1][0]
        literal = function.items[-1].items[1]
        self.assertEqual((literal.kind, literal.items), ('int', (42,)))
        self.assertEqual((literal.span.filename, literal.span.line, literal.span.column),
                         ('literal.eld', 2, 22))

    def test_syntax_and_unsupported_are_distinct(self):
        from source_syntax import Diagnostic, parse_source
        for source, code, column in (
            ('module m; fn f()->Int { 1 2 }', 'syntax', 27),
            ('module m; fn f()->Int { if true { 1 } else { 2 } }', 'unsupported', 25),
            ('module m; fn f()->Int { 1 + 2 }', 'unsupported', 27),
            ('module m; fn f()->Int { 1 + }', 'syntax', 29),
        ):
            with self.subTest(source=source), self.assertRaises(Diagnostic) as caught:
                parse_source(source, 'bad.eld')
            self.assertEqual(caught.exception.code, code)
            self.assertEqual(caught.exception.span.column, column)

    def test_lexical_failure_and_missing_delimiter_have_locations(self):
        from source_syntax import Diagnostic, parse_source
        for source, line, column in (
            ('module m;\n$', 2, 1),
            ('module m;\npub fn main()->Int {', 2, 21),
            ('module m;\nlet x="\\u{d800}";', 2, 8),
        ):
            with self.subTest(source=source), self.assertRaises(Diagnostic) as caught:
                parse_source(source, 'syntax.eld')
            self.assertEqual(caught.exception.code, 'syntax')
            self.assertEqual((caught.exception.span.line, caught.exception.span.column), (line, column))

    def test_nested_numeric_operators_remain_outside_literal_subset(self):
        from source_syntax import Diagnostic, parse_source
        with self.assertRaises(Diagnostic) as caught:
            parse_source('module m; pub fn main()->Int { -(-9223372036854775808) }')
        self.assertEqual(caught.exception.code, 'unsupported')


if __name__ == '__main__':
    unittest.main()
