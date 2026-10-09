module capture_free_fixed_region;

import state::ref::{Ref};

fn closed<@r>() ->{state<@r>} Int captures {} {
    42
}

pub fn main() -> Int {
    region local {
        let callback: fn() ->{state<@local>} Int captures {} = fn() -> Int {
            42
        };
        let cell: Ref<fn() ->{state<@local>} Int captures {}, @local> = Ref::new(callback);
        0
    }
}
