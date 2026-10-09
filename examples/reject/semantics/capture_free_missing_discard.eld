module capture_free_missing_discard;

import state::ref::{Ref};

fn ignore<T, @r>(cell: Ref<T, @r>) -> Unit where T: CaptureFree {}

pub fn main() -> Int {
    0
}
