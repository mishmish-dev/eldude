module rejects::capture_free_unused_enum;

import state::ref::{Ref};

enum Invalid<@r> {
    Cell(Ref<Ref<Int, @r>, @r>)
}

pub fn main() -> Int {
    42
}
