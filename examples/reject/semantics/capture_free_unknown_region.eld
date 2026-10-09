module capture_free_unknown_region;

import state::ref::{Ref};

pub fn main() -> Int {
    let cell: Ref<Int, @missing> = Ref::new(0);
    0
}
