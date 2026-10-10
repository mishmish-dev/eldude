module affine_capture_row;

import collections::dyn_array::{DynArray};

fn relay<
    @r,
    ..C
>(f: fn() ->{state<@r>} Int captures {..C}) -> fn() ->{state<@r>} Int captures {..C} {
    f
}

pub fn main() -> Int {
    region local {
        let values: DynArray<Int, @local> = DynArray::new();
        let f = relay(
            fn() ->{state<@local>} Int captures {values} {
                let frozen = values.freeze();
                42
            }
        );
        f()
    }
}

pub fn verify() -> Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
