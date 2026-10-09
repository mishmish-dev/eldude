"""Syntax conformance cases for the normative Eldude grammar, not type tests."""
import unittest
from pathlib import Path
from check_grammar import Grammar

GRAMMAR = Path(__file__).resolve().parents[1] / 'docs/eldude.ebnf'

class GrammarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.grammar = Grammar(GRAMMAR.read_text(encoding='utf-8'))

    def test_source_forms(self):
        cases = [
            'module m; fn f(x:Bool)->Unit { assert x; }',
            'module m; fn with(view xs:T)->Int { xs.tail } enum LinkedList<T> { Nil, Cons { head:T, tail:LinkedList<T> }, }',
            'module m; fn f()->Int { if unsafe { check() } { 1 } else { 0 } }',
            'module m; fn f()->Int { match try { load()? } { case Result::Ok(x)=>x; case Result::Err(_)=>0; } }',
            'module m; fn f(state:Int)->Unit { view values.with(0,fn(view item)=>inspect(view item)); }',
            'module m; pub import p::{T, f as g}; pub linear struct File;',
            'module m; pub struct Pair<T> { pub x: T, y: Int, } pub enum Maybe<T> { pub No, pub Yes(T), }',
            'module m; enum Expr<T> where { Lit: fn(Int) -> Expr<Int>, Pair: forall<A,B>. fn(Expr<A>,Expr<B>) -> Expr<(A,B)>, }',
            'module m; let id: forall<T>. fn(T)->T = fn(x)=>x; let f=fn(view x, mut y)=>read(view x, mut y);',
            'module m; trait Source { type Item; type Map<U>; fn next(mut self)->Option<Self::Item>; }',
            'module m; impl<T> Eq for List<T> where T: Eq { fn eq(self, other: List<T>)->Bool { true } }',
            'module m; impl<T> Source for Box<T> { type Item=T; type Map<U> = (T,U); fn next(mut self)->Option<T> { Option::None } }',
            'module m; fn f<T,F<_>,@r,!e,..C,#N>(view x:T, mut y:T, cb:fn(T)->{| e}T captures {..C})->{state<@r> | e}T where e:NonAbandoning, ..C:Dup+Discard { cb(x) }',
            'module m; fn f(x:Int)->Int { let y=-128i8; let z=1.25e-2f32; if x<0 { 0 } else { x+1 } }',
            'module m; fn f(xs:List<Int>)->Nat { for x in xs { use(x); }; while check() { continue; }; 0nat }',
            'module m; fn f(x:Option<Pair>)->Int { x.?left ?? 0 }',
            'module m; fn f(x:Pair)->Int { let Pair { left, right:_ }=x; match left { case 0 | 1 => 2; case n if n>2 => n; case _ => 0; } }',
            'module m; fn f()->Unit { using (a=open()?,b=open()?) { taskgroup { let t=spawn work(); await t; } } }',
            'module m; effect E<@r> { once get()->Int; affine stop()->Never; } fn f()->Int { handle { !E::get() } with h=handler E { get()=>resume(1); forward stop; return x=>x; } }',
            'module m; extern "C" { pub unsafe fn native(p:*const UInt8)->Int; } fn f()->Unit { unsafe { native(ptr); } }',
            'module m; type X=<T as Collection<A>>::Item<U>; let xs=[1,2,3]; let x=xs[0]; let p=Point { x:1,y:2 };',
            'module m; let add=fn(x)=>x+1; let x=(fn(x)=>x)(1); fn f()->Int { return g()+1; }',
            'module m; let t=(1<2)==true; /* comment */ let u=0; // EOF comment',
            'module m; let s="a\\n\\u{1f600}"; let c=\'\\u{41}\'; let bits=0xffu8;',
        ]
        for source in cases:
            with self.subTest(source=source):
                self.assertTrue(self.grammar.accepts(source), source)

    def test_concrete_tree_retains_tokens_and_distinguishes_braces(self):
        self.assertTrue(hasattr(self.grammar, 'parse_tokens'), 'concrete grammar parsing is missing')
        tokens = self.grammar.lex('module m; fn f()->{Log | e} Int { (1 + 2) }', 'source_file')
        tree, failure = self.grammar.parse_tokens(tokens)
        self.assertIsNone(failure)
        leaves, rules = [], []

        def visit(node):
            if isinstance(node, int):
                leaves.append(node)
            else:
                rules.append(node.name)
                for child in node.children:
                    visit(child)

        visit(tree)
        self.assertEqual(leaves, list(range(len(tokens))))
        self.assertEqual((tree.name, tree.start, tree.end), ('source_file', 0, len(tokens)))
        self.assertIn('effect_row', rules)
        self.assertIn('block', rules)
        self.assertIn('tuple_expr', rules)

    def test_concrete_tree_reports_the_same_syntax_failure(self):
        self.assertTrue(hasattr(self.grammar, 'parse_tokens'), 'concrete grammar parsing is missing')
        for source in ('module m; fn f()->Int { 1 + }', 'module m; fn f()->Int {'):
            tokens = self.grammar.lex(source, 'source_file')
            tree, failure = self.grammar.parse_tokens(tokens)
            self.assertIsNone(tree)
            self.assertEqual(failure, self.grammar.syntax_failure(tokens))

    def test_rejected_source_forms(self):
        for source in [
            'let x=1;',
            'module m; let mut x=1;',
            'module m; let x=fn(a)=>a; x=2;',
            'module m; let f=fn(x)=>x; let y=f(view make());',
            'module m; let x=1 < 2 < 3;',
            'module m; let x=1__2;',
            'module m; let x=\"\\u{d800}\";',
            'module m; let x=\"\\u{110000}\";',
            'module m; let x=\"\\q\";',
            'module m; type X<T>=T;',
            'module m; import p::*;',
            'module m; let x=handle {} with handler E {}; let h=handler E {};',
            'module m; let x=fn(a:Int)->Int { a } semantic { result-captures <= {}; };',
            'module m; fn f()->Unit { ... }',
        ]:
            with self.subTest(source=source):
                self.assertFalse(self.grammar.accepts(source), source)

    def test_interface_forms(self):
        source='module m; pub fn f(view x:T)->U; semantic { result-captures <= {captures(x),..C,@r}; finite-positive-parameters = {0,1}; mutable-owner-region = @r; }'
        self.assertTrue(self.grammar.accepts(source, 'interface_file'))
        self.assertFalse(self.grammar.accepts(source, 'source_file'))

    def test_applied_effect_contracts_and_operations(self):
        source = 'module m; effect Store<T> { tail put(value:T)->Unit; once get()->T; } fn put(value:Int)->{Store<Int>} Unit { !Store::<Int>::put(value); } fn run()->Int { handle { !Store::<Int>::get() } with store=handler Store<Int> { put(value)=>(); get()=>resume(1); } }'
        self.assertTrue(self.grammar.accepts(source))
        self.assertTrue(self.grammar.accepts('module m; fn f<@r,!e>()->{Store<Ref<Int,@r>>,state<@r> | e} Unit;'))
        self.assertFalse(self.grammar.accepts(source.replace('Store::<Int>::put', 'Store<Int>::put')))

    def test_single_tail_effect_rows(self):
        for row in ('{}', '{Log}', '{Log, Log}', '{| e}', '{Log | e}',
                    '{Store<Int>, Store<Bool>, suspend | e}'):
            with self.subTest(row=row):
                self.assertTrue(self.grammar.accepts(row, 'effect_row'))
        for row in ('{|}', '{Log | e, f}', '{Log | e | f}', '{| e,}',
                    '{Log, | e}', '{Log | Store<Int>}'):
            with self.subTest(row=row):
                self.assertFalse(self.grammar.accepts(row, 'effect_row'))

    def test_tail_handler_return_syntax(self):
        # Operation modes are resolved by typing, not by the grammar recognizer.
        source = ('module m; effect Read { tail read()->Int; } '
                  'fn f()->Int { handle { !Read::read() } with handler Read { '
                  'read()=>{ if true { return 42; }; 0 } } }')
        self.assertTrue(self.grammar.accepts(source))

    def test_termination_measures_are_deferred(self):
        for source in (
            'module m; fn f(n:Nat)->Nat decreases n { n }',
            'module m; trait T { fn f(self)->Unit decreases 0nat; }',
            'module m; impl T { fn f(self)->Unit decreases 0nat {} }',
            'module m; fn f()->Unit { while ready() decreases n {} }',
            'module m; fn f(xs:List<Int>)->Unit { for x in xs decreases n {} }',
        ):
            for entry in ('source_file', 'interface_file'):
                with self.subTest(source=source, entry=entry):
                    self.assertFalse(self.grammar.accepts(source, entry))

    def test_termination_contract_syntax(self):
        # These check syntax; termination/effect validity requires a type checker.
        for source in (
            'module m; fn gcd(a:Nat,b:Nat)->{diverge} Nat { if b==0nat { a } else { gcd(b,a%b) } }',
            'module m; fn f()->{diverge} Unit { while ready() {} }',
            'module m; fn f(xs:List<Int>)->Unit { for x in xs { use(x); } }',
            'module m; fn decreases(value:Int)->Int { value }',
        ):
            with self.subTest(source=source):
                self.assertTrue(self.grammar.accepts(source))

    def test_nonfinal_loops_require_expression_separators(self):
        for loop in ('while condition {}', 'for x in xs {}'):
            with self.subTest(loop=loop):
                self.assertTrue(self.grammar.accepts('module m; fn f()->Int { '+loop+'; 1 }'))
                self.assertTrue(self.grammar.accepts('module m; fn f()->Unit { '+loop+' }'))
                self.assertFalse(self.grammar.accepts('module m; fn f()->Int { '+loop+' 1 }'))

    def test_whole_value_capture_and_opaque_usage_interfaces(self):
        interface = 'module m; pub struct Box<T>; semantic { representation=opaque; usage { Dup=(T:Dup); Discard=(T:Discard); } } pub enum Status { pub Ready, } semantic { representation=opaque; usage { Dup=true; Discard=true; } } pub fn first(pair:(any Show+Discard,any Show+Discard))->any Show+Discard; semantic { result-captures <= {captures(parameter(0))}; } pub fn field(view pair:Pair)->any Show+Discard; semantic { result-captures <= {captures(pair)}; }'
        self.assertTrue(self.grammar.accepts(interface, 'interface_file'))
        self.assertFalse(self.grammar.accepts(interface, 'source_file'))
        self.assertFalse(self.grammar.accepts(interface.replace('parameter(0)', 'parameter()'), 'interface_file'))
        self.assertFalse(self.grammar.accepts(interface.replace('Dup=(T:Dup)', 'Dup='), 'interface_file'))

    def test_capture_projections_and_payload_contracts_are_deferred(self):
        for bound in ('{captures(parameter(0).component(0))}',
                      '{captures(pair.member(m::Pair::first))}',
                      '{captures(parameter(0).payload)}'):
            with self.subTest(bound=bound):
                self.assertFalse(self.grammar.accepts(bound, 'capture_bound'))
        for clause in ('payload-captures=tracked;',
                       'payload-captures <= {captures(parameter(0))};'):
            with self.subTest(clause=clause):
                interface = 'module m; pub struct Box<T>; semantic { '+clause+' }'
                self.assertFalse(self.grammar.accepts(interface, 'interface_file'))

    def test_member_and_nested_callable_interfaces(self):
        interface = 'module m; pub trait Factory<T> { fn first(self,x:T)->any Show; fn second(self,y:T)->any Show; } semantic { member(m::Factory::first) { result-captures <= {captures(x)}; } member(m::Factory::second) { result-captures <= {captures(y)}; } } impl<T> Factory<T> for Holder<T> { fn first(self,x:T)->any Show; fn second(self,y:T)->any Show; } semantic { member(m::Factory::first) { result-captures <= {captures(parameter(1))}; } member(m::Factory::second) { result-captures <= {captures(parameter(1)),captures(..)}; } } pub fn apply(f:fn(T)->U)->U; semantic { parameter(0) { result-captures <= {captures(parameter(0)),captures(..)}; } }'
        self.assertTrue(self.grammar.accepts(interface, 'interface_file'))
        self.assertFalse(self.grammar.accepts(interface, 'source_file'))
        self.assertFalse(self.grammar.accepts(interface.replace('member(m::Factory::first)', 'member(0)'), 'interface_file'))

    def test_mutable_owner_and_finite_iteration_interfaces(self):
        interface = 'module m; pub struct Buffer<T,@r>; semantic { representation=opaque; usage { Dup=false; Discard=(T:Discard); } mutable-owner-region=@r; } impl<T,@r> Buffer<T,@r> { pub fn freeze(self)->List<T>; pub fn push(mut self,value:T)->Unit; } semantic { member(m::Buffer::freeze) { result-captures <= {captures(parameter(0))}; } member(m::Buffer::push) { result-captures <= {}; } } impl<T> Iterator for List<T> { type Item=T; fn next(self)->Next<List<T>,T>; } semantic { finite-iteration=true; }'
        self.assertTrue(self.grammar.accepts(interface, 'interface_file'))
        self.assertFalse(self.grammar.accepts(interface, 'source_file'))
        self.assertFalse(self.grammar.accepts(interface.replace('finite-iteration=true', 'finite-iteration=maybe'), 'interface_file'))

    def test_ffi_interface_forms(self):
        source = 'module native; pub fn call(cb:fn()->Unit)->Unit; semantic { ffi-contract { invocation=synchronous; parameter(0) { callback { barrier=ordinary; defect=protocol(native::Rendezvous); pending-defect-entry=suppressed; } } result { pointer { ownership=transferred_to_eldude; provenance={@r}; } } member(native::close) { invocation=synchronous; } } ffi-protocol native::Rendezvous="Private ABI control path."; }'
        self.assertTrue(self.grammar.accepts(source, 'interface_file'))
        self.assertFalse(self.grammar.accepts(source, 'source_file'))
        aggregate = 'module m; pub fn register(pair:(fn()->Unit, fn()->Unit))->Unit; semantic { ffi-contract { parameter(0) { component(0) { callback { cardinality=exactly_once; } } component(1) { callback { cardinality=may_skip; } } } } } pub enum E { pub V(fn()->Unit), } semantic { ffi-contract { member(m::E::V) { component(0) { callback { cardinality=may_repeat; } } } } }'
        self.assertTrue(self.grammar.accepts(aggregate, 'interface_file'))
        self.assertFalse(self.grammar.accepts(aggregate, 'source_file'))
        for malformed in [source.replace('barrier=ordinary;', 'barrier ordinary;'),
                          source.replace('parameter(0)', 'parameter(callback)'),
                          source.replace('ffi-protocol native::Rendezvous=', 'ffi-protocol=')]:
            self.assertFalse(self.grammar.accepts(malformed, 'interface_file'))

    def test_grammar_validation(self):
        with self.assertRaises(ValueError):
            Grammar('source_file ::= missing;')
        with self.assertRaises(ValueError):
            Grammar('source_file ::= "x"; source_file ::= "y";')

if __name__ == '__main__':
    unittest.main()
