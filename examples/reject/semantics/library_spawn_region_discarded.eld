module library_spawn_region_discarded;

import state::ref::{Ref};

pub fn main() ->{suspend} Int {
    taskgroup {
        region local {
            let cell: Ref<Int, @local> = Ref::new(42);
            spawn {
                let retained = cell;
                42
            };
        };
        42
    }
}
