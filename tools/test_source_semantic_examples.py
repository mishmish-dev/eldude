"""Exercise semantic rejection examples beyond the runner's entry-point check."""
from pathlib import Path
import re
import unittest

from source_pipeline import compile_source
from source_syntax import Diagnostic

ROOT = Path(__file__).resolve().parents[1]
REJECT = ROOT / 'examples' / 'reject' / 'semantics'


def executable_source(path):
    source = path.read_text(encoding='utf-8')
    if not re.search(r'\bpub\s+fn\s+main\b', source):
        if re.search(r'\bfn\s+main\b', source):
            source = re.sub(r'\bfn\s+main\b', 'pub fn main', source, count=1)
        else:
            source += '\npub fn main() -> Int { 42 }\n'
    return source


class SourceSemanticExampleTests(unittest.TestCase):
    def test_rejection_examples_reach_their_semantic_check(self):
        cases = {
            'linear_discard': ('semantic', 'Unconsumed resource ticket'),
            'parameter_capture_twice': ('semantic', 'already consumed'),
            'parameter_capture_escape': ('semantic', 'region would escape'),
            'inherited_answer_change': ('semantic', 'Inherited handler'),
            'numeric_recursion_without_diverge': ('effect', 'structural descent or diverge'),
            'region_escape': ('semantic', 'region would escape'),
            'freeze_captured_elements': ('semantic', 'region would escape'),
            'while_without_diverge': ('effect', 'declared effect row'),
            'uncovered_impl': ('semantic', 'Uncovered implementation parameter'),
            'tail_explicit_resume': ('semantic', 'resume is forbidden'),
            'row_variable_entry': ('name', 'Unknown effect family e'),
            'whole_argument_capture': ('semantic', 'region would escape'),
            'await_whole_argument_capture': ('semantic', 'region would escape'),
            'mut_capture_escape': ('semantic', 'mutable owner'),
            'trait_missing_prerequisite': ('semantic', 'Missing trait evidence'),
            'trait_overlap': ('semantic', 'Overlapping'),
            'trait_constraint_cycle': ('semantic', 'decrease'),
            'trait_stronger_method': ('semantic', 'stronger'),
        }
        for name, (code, message) in cases.items():
            path = REJECT / (name + '.eld')
            with self.subTest(example=name):
                with self.assertRaises(Diagnostic) as caught:
                    compile_source(executable_source(path), str(path))
                self.assertEqual(caught.exception.code, code, str(caught.exception))
                self.assertIn(message, caught.exception.message)
                self.assertEqual(caught.exception.span.filename, str(path))

    def test_trait_members_match_declared_associated_types(self):
        source = '''module m;
trait Value { type Output; fn value(self) -> Self::Output; }
struct Box {}
impl Value for Box {
    type Output = Int;
    fn value(self) -> Bool { true }
}
pub fn main() -> Int { 42 }
'''
        with self.assertRaises(Diagnostic) as caught:
            compile_source(source)
        self.assertEqual(caught.exception.code, 'type')
        self.assertIn('trait declaration', caught.exception.message)

    def test_record_annotation_cannot_change_constructor_identity(self):
        source = 'module m; struct A{x:Int} struct B{x:Int} pub fn main()->Int{let a:A=B{x:42};a.x}'
        with self.assertRaises(Diagnostic) as caught:
            compile_source(source)
        self.assertEqual(caught.exception.code, 'type')
        self.assertIn('nominal type', caught.exception.message)

    def test_termination_proof_requires_fixed_unshadowed_descent(self):
        bodies = (
            'match a {case C::End=>42;case C::Link(rest)=>walk(b,rest);}',
            'let alias=walk; alias(a,b)',
            'match a {case C::End=>42;case C::Link(rest)=>{let rest=a; walk(rest,b)};}',
        )
        for body in bodies:
            source = 'module m; enum C{End,Link(C)} fn walk(a:C,b:C)->Int {' + body + '} pub fn main()->Int {42}'
            with self.subTest(body=body):
                with self.assertRaises(Diagnostic) as caught:
                    compile_source(source)
                self.assertEqual(caught.exception.code, 'effect')
                self.assertIn('structural descent or diverge', caught.exception.message)


if __name__ == '__main__':
    unittest.main()
