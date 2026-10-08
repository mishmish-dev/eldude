module explicit_regions;
import state::ref::{Ref};
fn call<@a,@b>(f:fn()->{state<@a>,state<@b>}Int captures {@a,@b})->{state<@a>,state<@b>}Int {f()}
fn relay<..C>(f:fn()->Int captures {..C})->fn()->Int captures {..C} {f}
pub fn main()->Int {region outer {region inner {
    let x:Ref<Int,@outer> = Ref::new(20);
    let y:Ref<Int,@inner> = Ref::new(22);
    let f=fn()->{state<@outer>,state<@inner>}Int captures {x,y} {x.get()+y.get()};
    let pure=relay::<{@outer}>(fn()->Int captures {x} {let copy=x;0});
    let ignored=pure();
    let empty=relay::<{}>(fn()->Int {0});
    let ignoredEmpty=empty();
    call::<@outer,@inner>(f)
}}}
