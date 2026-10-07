module inferred_regions;
import state::ref::{Ref};
fn call<@a,@b>(f:fn(Ref<Int,@a>)->{state<@b>}Int captures {@b},x:Ref<Int,@a>)->{state<@b>}Int {f(x)}
fn reverse<@a,@b>(x:Ref<Int,@a>,f:fn(Ref<Int,@a>)->{state<@b>}Int captures {@b})->{state<@b>}Int {f(x)}
pub fn main()->Int {region outer {region inner {
    let x:Ref<Int,@outer> = Ref::new(0);
    let y:Ref<Int,@inner> = Ref::new(21);
    let read=fn(unused:Ref<Int,@outer>)->{state<@inner>}Int captures {y} {y.get()};
    call(read,x)+reverse(x,read)
}}}
