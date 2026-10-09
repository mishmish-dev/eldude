module ambiguous_callback_regions;

import state::ref::{Ref};

fn call<
    @a,
    @b
>(f: fn() ->{state<@a>, state<@b>} Int captures {@a, @b}) ->{state<@a>, state<@b>} Int {
    f()
}

pub fn main() -> Int {
    region outer {
        region inner {
            let x: Ref<Int, @outer> = Ref::new(20);
            let y: Ref<Int, @inner> = Ref::new(22);
            call(fn() ->{state<@outer>, state<@inner>} Int captures {x, y} {
                x.get() + y.get()
            })
        }
    }
}
