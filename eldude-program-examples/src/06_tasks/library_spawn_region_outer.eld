module library_spawn_region_outer;

import state::ref::{Ref};

pub fn main() ->{suspend} Int {
    region local {
        let cell: Ref<Int, @local> = Ref::new(0);
        taskgroup {
            spawn {
                cell.replace(42);
            };
        };
        cell.get()
    }
}

pub fn verify() ->{suspend} Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
