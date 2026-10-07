"""Located AST coverage for the executable corpus and bundled declarations."""
from pathlib import Path
import unittest

from source_syntax import Diagnostic, Node, parse_source

ROOT = Path(__file__).resolve().parents[1]


def nodes(value):
    if isinstance(value, Node):
        yield value
        yield from nodes(value.items)
    elif isinstance(value, tuple):
        for item in value:
            yield from nodes(item)


class ExtendedSourceSyntaxTests(unittest.TestCase):
    def test_all_examples_and_bundled_sources_have_located_ast(self):
        examples = [p for p in (ROOT / 'examples').rglob('*.eld') if 'reject' not in p.parts]
        self.assertEqual(len(examples), 52)
        for path in examples + list((ROOT / 'stdlib').rglob('*.eld')):
            with self.subTest(path=path.relative_to(ROOT)):
                source = path.read_text(encoding='utf-8')
                ast = parse_source(source, str(path))
                self.assertEqual(ast.kind, 'module')
                for node in nodes(ast):
                    span = node.span
                    self.assertEqual(span.filename, str(path))
                    self.assertTrue(0 <= span.start < span.end <= len(source), node)
                    self.assertEqual(span.line, source.count('\n', 0, span.start) + 1)
                    self.assertEqual(span.column, span.start - source.rfind('\n', 0, span.start))

    def test_syntax_rejection_still_uses_normative_grammar(self):
        for path in (ROOT / 'examples' / 'reject' / 'syntax').rglob('*.eld'):
            with self.subTest(path=path), self.assertRaises(Diagnostic) as caught:
                parse_source(path.read_text(encoding='utf-8'), str(path))
            self.assertEqual(caught.exception.code, 'syntax')

    def test_semantic_counterexamples_are_not_rejected_by_parser(self):
        for path in (ROOT / 'examples' / 'reject' / 'semantics').rglob('*.eld'):
            with self.subTest(path=path):
                self.assertEqual(parse_source(path.read_text(), str(path)).kind, 'module')

    def test_generic_contract_and_declaration_metadata(self):
        ast = parse_source('''module m;
linear struct Guard<T, @r> { value: T }
trait Value { type Output; fn value(view self) -> Self::Output; }
impl<T, @r> Value for Guard<T, @r> where T: Discard {
    type Output = T;
    fn value(view self) -> T;
}
fn invoke<T, @r, !e, ..C>(mut value: Guard<T, @r>,
    f: fn(view T) ->{| e} T captures {..C})
    ->{state<@r>, suspend | e} T captures {@r} where T = Int;
''')
        struct, trait, impl, function = ast.items[1]
        self.assertEqual(struct.items[-1], 'linear')
        self.assertEqual(struct.items[1].items[1][1].items[0], '@')
        self.assertEqual(trait.items[2][0].kind, 'associated_type')
        self.assertEqual(impl.items[2].kind, 'applied_type')
        self.assertEqual(impl.items[3][0].kind, 'bound')
        self.assertIsNone(function.items[-1])
        self.assertEqual(len(function.items), 5)
        self.assertEqual(function.items[1].items[2][0].kind, 'type_equality')
        self.assertEqual(function.items[2][0].items[2], 'mut')
        contract = function.items[3]
        self.assertEqual([n.kind for n in contract.items[1]], ['applied_type', 'path', 'effect_tail'])
        self.assertEqual(contract.items[2][0].kind, 'region_type')

    def test_patterns_guards_nat_and_access_nodes(self):
        source = '''module m;
enum Choice<T> { Empty, Pair(T, T), Named { value: T } }
fn f(value: Choice<Nat>) -> Nat {
    match value {
        case Choice::Pair(0nat | 1nat, rest) if rest > 0nat => rest;
        case Choice::Named { value: result } => result;
        case Choice::Empty => 0nat;
        case _ => 2nat;
    }
}
fn inspect(view value: Choice<Nat>) -> Nat { f(view value) }
'''
        ast = parse_source(source, 'patterns.eld')
        enum, function, inspect = ast.items[1]
        self.assertEqual([n.items[3] for n in enum.items[2]], ['unit', 'tuple', 'record'])
        match = function.items[-1].items[1]
        self.assertEqual(match.kind, 'match')
        arms = match.items[1]
        self.assertEqual(arms[0].items[0].items[1][0].kind, 'or_pattern')
        self.assertEqual(arms[0].items[1].kind, 'binary')
        self.assertEqual(arms[1].items[0].kind, 'record_pattern')
        literal = next(n for n in nodes(ast) if n.kind == 'nat')
        self.assertEqual(source[literal.span.start:literal.span.end], '0nat')
        self.assertEqual(inspect.items[-1].items[1].items[1][0].kind, 'access')

    def test_control_flow_postfix_and_coalesce_precedence(self):
        ast = parse_source('''module m;
fn f()->{suspend, diverge} Int {
    region local {
        let xs = [1, 2];
        for x in xs { view xs.length(); };
        while false { break; };
        taskgroup { let task = spawn 1; await task };
        try { return xs[0]? ?? 2 ?? 3; }
    }
}
''')
        found = list(nodes(ast))
        for kind in ('region', 'list', 'for', 'while', 'break', 'access_method',
                     'taskgroup', 'spawn', 'await', 'try', 'return', 'index', 'propagate'):
            self.assertIn(kind, [n.kind for n in found])
        coalescing = next(n for n in found if n.kind == 'binary' and n.items[0] == '??')
        self.assertEqual(coalescing.items[1].kind, 'propagate')
        self.assertEqual(coalescing.items[2].items[0], '??')

    def test_generic_effect_instances_keep_arguments_and_operation(self):
        ast = parse_source('''module m;
effect Read<T> { tail value() -> T; }
fn f()->Int { handle { !Read::<Int>::value() } with handler Read<Int> { value() => 42; } }
''')
        handle = ast.items[1][1].items[-1].items[1]
        self.assertEqual(handle.items[0].kind, 'applied_type')
        perform = handle.items[2].items[1]
        self.assertEqual(perform.items[0].kind, 'operation_path')
        self.assertEqual(perform.items[0].items[0].items[0], 'Read')
        self.assertEqual(perform.items[0].items[1].items[0], 'value')


if __name__ == '__main__':
    unittest.main()
