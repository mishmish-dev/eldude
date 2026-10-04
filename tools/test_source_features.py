"""Execution contracts for the remaining staged language examples."""
import json
import unittest
from pathlib import Path

from source_pipeline import compile_source, execute_file
from source_syntax import Diagnostic
from handlers import run

ROOT = Path(__file__).resolve().parents[1]


class ExtendedSourceTests(unittest.TestCase):
    def test_all_staged_examples_execute(self):
        manifest = json.loads((ROOT / 'examples/manifest.json').read_text())
        for name, expected in (manifest['runnable'] | manifest['pending']).items():
            with self.subTest(example=name):
                self.assertEqual(execute_file(ROOT / 'examples' / name).value, expected)

    def execute(self, source):
        return run(compile_source(source).program)

    def test_enum_match_is_exhaustive_and_nominal(self):
        for source in (
            'module m; enum E {A,B} pub fn main()->Int {match E::A {case E::A=>42;}}',
            'module m; enum E {A} enum F {A} fn f(x:E)->Int {42} pub fn main()->Int {f(F::A)}',
        ):
            with self.subTest(source=source), self.assertRaises(Diagnostic):
                compile_source(source)

    def test_unproved_numeric_recursion_requires_diverge(self):
        source = '''module m; fn count(n:Nat)->Nat {
if n==0nat {0nat} else {count(n-1nat)}} pub fn main()->Nat {count(3nat)}'''
        with self.assertRaises(Diagnostic) as caught:
            compile_source(source)
        self.assertIn('diverge', str(caught.exception))

    def test_while_admits_diverge_and_executes_regional_state(self):
        source = '''module m; import state::ref::{Ref};
pub fn main()->{diverge} Int {region r {
let n:Ref<Int,@r> = Ref::new(0);
while n.get()<1200 {n.replace(n.get()+1);}; n.get()
}}'''
        self.assertEqual(self.execute(source).value, 1200)
        with self.assertRaises(Diagnostic) as caught:
            compile_source(source.replace('->{diverge}', '->'))
        self.assertEqual(caught.exception.code, 'effect')

    def test_region_and_task_handles_do_not_escape(self):
        for source in (
            'module m; import state::ref::{Ref}; pub fn main()->Int {let f=region r {let x:Ref<Int,@r>=Ref::new(42); fn()=>x.get()};f()}',
            'module m; pub fn main()->{suspend} Int {let t=taskgroup {spawn 42};await t}',
        ):
            # Keep the generic close delimiter separate from the initializer.
            source = source.replace('@r>=', '@r> =')
            with self.subTest(source=source), self.assertRaises(Diagnostic):
                compile_source(source)

    def test_affine_record_cannot_discard_a_linear_field(self):
        source = '''module m; import eldude::fixture::{File,acquire};
affine struct Box { f:File }
pub fn main()->Int {let b=Box{f:acquire()};42}'''
        with self.assertRaises(Diagnostic) as caught:
            compile_source(source)
        self.assertIn('Unconsumed', caught.exception.message)


if __name__ == '__main__':
    unittest.main()
