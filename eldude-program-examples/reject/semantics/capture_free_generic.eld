module capture_free_generic;

import state::ref::{Ref};

fn ignore<T, @r>(cell: Ref<T, @r>) -> Unit where T: Discard {}

pub fn main() -> Int {
    0
}
