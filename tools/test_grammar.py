"""Syntax conformance cases for the normative Eldude grammar, not type tests."""
import unittest
from pathlib import Path
from check_grammar import Grammar

GRAMMAR = Path(__file__).resolve().parents[1] / 'design-docs/eldude.ebnf'

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
            'module m; fn f<T,F<_>,@r,!e,..C,#N>(view x:T, mut y:T, cb:fn(T)->{e}T captures {..C})->{state<@r>,e}T where e:NonAbandoning, ..C:Dup+Discard decreases N { cb(x) }',
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
        source = 'module m; effect Store<T> { tail put(value:T)->Unit; once get()->T; } fn put(value:Int)->{Store<Int>} Unit { !Store::<Int>::put(value); } fn run()->Int { handle { !Store::<Int>::get() } with store=handler Store<Int> { put(value)=>resume(()); get()=>resume(1); } }'
        self.assertTrue(self.grammar.accepts(source))
        self.assertTrue(self.grammar.accepts('module m; fn f<@r,!e>()->{Store<Ref<Int,@r>>,state<@r>,e} Unit;'))
        self.assertFalse(self.grammar.accepts(source.replace('Store::<Int>::put', 'Store<Int>::put')))

    def test_nonfinal_loops_require_expression_separators(self):
        for loop in ('while condition {}', 'for x in xs {}'):
            with self.subTest(loop=loop):
                self.assertTrue(self.grammar.accepts('module m; fn f()->Int { '+loop+'; 1 }'))
                self.assertTrue(self.grammar.accepts('module m; fn f()->Unit { '+loop+' }'))
                self.assertFalse(self.grammar.accepts('module m; fn f()->Int { '+loop+' 1 }'))

    def test_component_capture_and_opaque_usage_interfaces(self):
        interface = 'module m; pub struct Box<T>; semantic { representation=opaque; usage { Dup=(T:Dup); Discard=(T:Discard); } } pub enum Status { pub Ready, } semantic { representation=opaque; usage { Dup=true; Discard=true; } } pub fn first(pair:(any Show+Discard,any Show+Discard))->any Show+Discard; semantic { result-captures <= {captures(parameter(0).component(0))}; } pub fn field(view pair:Pair)->any Show+Discard; semantic { result-captures <= {captures(pair.member(m::Pair::first))}; }'
        self.assertTrue(self.grammar.accepts(interface, 'interface_file'))
        self.assertFalse(self.grammar.accepts(interface, 'source_file'))
        self.assertFalse(self.grammar.accepts(interface.replace('component(0)', 'component()'), 'interface_file'))
        self.assertFalse(self.grammar.accepts(interface.replace('Dup=(T:Dup)', 'Dup='), 'interface_file'))

    def test_member_and_nested_callable_interfaces(self):
        interface = 'module m; pub trait Factory<T> { fn first(self,x:T)->any Show; fn second(self,y:T)->any Show; } semantic { member(m::Factory::first) { result-captures <= {captures(x)}; } member(m::Factory::second) { result-captures <= {captures(y)}; } } impl<T> Factory<T> for Holder<T> { fn first(self,x:T)->any Show; fn second(self,y:T)->any Show; } semantic { member(m::Factory::first) { result-captures <= {captures(parameter(1))}; } member(m::Factory::second) { result-captures <= {captures(parameter(1)),captures(..)}; } } pub fn apply(f:fn(T)->U)->U; semantic { parameter(0) { result-captures <= {captures(parameter(0)),captures(..)}; } }'
        self.assertTrue(self.grammar.accepts(interface, 'interface_file'))
        self.assertFalse(self.grammar.accepts(interface, 'source_file'))
        self.assertFalse(self.grammar.accepts(interface.replace('member(m::Factory::first)', 'member(0)'), 'interface_file'))

    def test_owned_payload_and_finite_iteration_interfaces(self):
        interface = 'module m; pub struct Buffer<T,@r>; semantic { representation=opaque; usage { Dup=false; Discard=(T:Discard); } payload-captures=tracked; mutable-owner-region=@r; } impl<T,@r> Buffer<T,@r> { pub fn freeze(self)->List<T>; pub fn push(mut self,value:T)->Unit; } semantic { member(m::Buffer::freeze) { result-captures <= {captures(parameter(0).payload)}; } member(m::Buffer::push) { parameter(0) { payload-captures <= {captures(parameter(0).payload),captures(parameter(1))}; } } } impl<T> Iterator for List<T> { type Item=T; fn next(self)->Next<List<T>,T>; } semantic { finite-iteration=true; }'
        self.assertTrue(self.grammar.accepts(interface, 'interface_file'))
        self.assertFalse(self.grammar.accepts(interface, 'source_file'))
        self.assertFalse(self.grammar.accepts(interface.replace('.payload', '.payload(0)'), 'interface_file'))
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
