module rejects::capture_free_unused_record;

import state::ref::{Ref};

struct Invalid<@r> {
    cell: Ref<Ref<Int, @r>, @r>
}

pub fn main() -> Int {
    42
}
