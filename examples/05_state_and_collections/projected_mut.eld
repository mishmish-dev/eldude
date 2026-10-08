module projected_mut;
import collections::dyn_array::{DynArray};
import core::option::{Option};
import state::ref::{Ref};
pub fn main()->Int {region inner {region outer {
    let innerValues:DynArray<Int,@inner> = DynArray::new();
    let values:DynArray<DynArray<Int,@inner>,@outer> = DynArray::new();
    mut values.push(innerValues);
    let found=mut values.withMut(0,fn(mut item:DynArray<Int,@inner>)->{state<@inner>}Int {
        mut item.push(42);
        match mut item.pop() {case Option::Some(n)=>n;case Option::None=>0;}
    });
    let counter:Ref<Int,@inner> = Ref::new(0);
    let missing=mut values.withMut(99,fn(mut item:DynArray<Int,@inner>)->{state<@inner>}Int captures {counter} {
        counter.replace(1);0
    });
    match found {case Option::Some(n)=>n+counter.get();case Option::None=>0;}
}}}
