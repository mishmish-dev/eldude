module examples::state_and_collections::local_state;

import state::ref::{Ref};

pub fn main() -> Int {
    region local {
        let cell: Ref<Int, @local> = Ref::new(40);
        cell.replace(cell.get() + 2);
        cell.get()
    }
}

pub fn verify() -> Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
