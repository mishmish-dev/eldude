module capture_free_nested_cell;

import state::ref::{Ref};

pub fn main() -> Int {
    region local {
        let inner: Ref<Int, @local> = Ref::new(42);
        let outer: Ref<Ref<Int, @local>, @local> = Ref::new(inner);
        0
    }
}
