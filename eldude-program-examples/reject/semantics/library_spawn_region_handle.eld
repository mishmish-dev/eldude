module library_spawn_region_handle;

import state::ref::{Ref};

pub fn main() ->{suspend} Int {
    taskgroup {
        let task = region local {
            let cell: Ref<Int, @local> = Ref::new(42);
            spawn {
                let retained = cell;
                42
            }
        };
        await task
    }
}
