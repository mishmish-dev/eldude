"""Ownership and nominal/generic dispatch contracts across source and runtime."""
import unittest

from eldude.handlers import _Slot, _read, compile_program, run
from eldude.inference import E, Ty
from eldude.source_features import FeatureChecker, Variant
from eldude.source_pipeline import compile_source
from eldude.source_syntax import Diagnostic


class SourceOwnershipBoundaryTests(unittest.TestCase):
    def test_nominal_enum_runtime_reads_consume_linear_and_affine_values(self):
        for usage in ('Linear', 'Affine'):
            checker = FeatureChecker()
            checker.variants = {'Enum:Ticket': {'Ready': ()}}
            t = Ty(usage, (Ty('Enum:Ticket'),))
            retained = run(compile_program(E('variant', t, 'Ready', ()), checker=checker)).value
            environment = {'ticket': _Slot(retained)}
            with self.subTest(usage=usage):
                self.assertIs(_read('ticket', environment), retained)
                with self.assertRaisesRegex(RuntimeError, 'Consumed runtime binding'):
                    _read('ticket', environment)

    def test_untyped_primitive_variant_still_uses_payload_ownership(self):
        retained = Variant(None, 'Ok', (42,))
        environment = {'answer': _Slot(retained)}
        self.assertIs(_read('answer', environment), retained)
        self.assertIs(_read('answer', environment), retained)

    def test_generic_record_with_concrete_dup_fields_is_reusable(self):
        source = '''module m;
struct Box<T> {item:T}
fn val(b:Box<Int>)->Int {b.item}
pub fn main()->Int {let b=Box{item:21};val(b)+val(b)}'''
        self.assertEqual(run(compile_source(source).program).value, 42)

    def test_enum_usage_qualifiers_prevent_duplicate_source_reads(self):
        for usage in ('linear', 'affine'):
            source = f'''module m;
{usage} enum Ticket {{One(Int)}}
pub fn main()->Int {{
let t=Ticket::One(21);
let a=match t {{case Ticket::One(n)=>n;}};
let b=match t {{case Ticket::One(n)=>n;}};
a+b
}}'''
            with self.subTest(usage=usage), self.assertRaises(Diagnostic):
                compile_source(source)

    def test_owned_enum_payload_cannot_be_discarded_or_duplicated(self):
        bodies = (
            'let e=E::V(acquire());42',
            '''let e=E::V(acquire()); let a=e; let b=e;
match a {case E::V(f)=>close(f);}; match b {case E::V(f)=>close(f);};42''',
        )
        for body in bodies:
            source = '''module m;
import eldude::fixture::{File,acquire,close};
enum E {V(File)}
pub fn main()->Int {''' + body + '}'
            with self.subTest(body=body), self.assertRaises(Diagnostic):
                compile_source(source)

    def test_repeated_enum_type_parameter_requires_matching_payloads(self):
        source = '''module m;
enum Pair<T> {Pair(T,T)}
pub fn main()->Bool {
let p=Pair::Pair(1,true);
match p {case Pair::Pair(a,b)=>a;}
}'''
        with self.assertRaises(Diagnostic):
            compile_source(source)

    def test_non_scalar_enum_payload_cannot_cross_scalar_operation_boundary(self):
        source = '''module m;
import eldude::fixture::{File};
enum E {V(File)}
effect X {tail get()->E;}
pub fn main()->Int {42}'''
        with self.assertRaisesRegex(Diagnostic, 'scalar'):
            compile_source(source)

    def test_duplicate_trait_implementations_are_rejected(self):
        source = '''module m;
trait V {fn value(self)->Int;}
struct Box {}
impl V for Box {fn value(self)->Int {1}}
impl V for Box {fn value(self)->Int {42}}
pub fn main()->Int {Box{}.value()}'''
        with self.assertRaises(Diagnostic):
            compile_source(source)

    def test_disjoint_specialized_dispatch_reports_its_explicit_limit(self):
        source = '''module m;
struct Box<T> {item:T}
impl Box<Int> {fn value(self)->Int {self.item}}
impl Box<Bool> {fn value(self)->Int {if self.item {21} else {0}}}
pub fn main()->Int {Box{item:21}.value()+Box{item:true}.value()}'''
        with self.assertRaises(Diagnostic) as caught:
            compile_source(source)
        self.assertEqual(caught.exception.code, 'unsupported')
        self.assertIn('specialized', caught.exception.message)

    def test_consuming_user_method_rejects_explicit_borrowed_access(self):
        for access in ('view', 'mut'):
            source = '''module m;
linear struct Ticket {n:Int}
impl Ticket {fn redeem(self)->Int {let Ticket{n}=self;n}}
pub fn main()->Int {let t=Ticket{n:42};''' + access + ' t.redeem()}'
            with self.subTest(access=access), self.assertRaises(Diagnostic):
                compile_source(source)


if __name__ == '__main__':
    unittest.main()
