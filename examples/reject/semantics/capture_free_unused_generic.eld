module rejects::capture_free_unused_generic;

import state::ref::{Ref};

struct Invalid<T, @r> {
    cell: Ref<T, @r>
}

pub fn main() -> Int {
    42
}
