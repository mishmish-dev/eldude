module examples::state_and_collections::finite_loop;

import collections::list::{List};
import core::iter::{Iterator};
import state::ref::{Ref};

pub fn main() -> Int {
    region local {
        let total: Ref<Int, @local> = Ref::new(0);
        for item in [10, 20, 12] {
            total.replace(total.get() + item);
        };
        total.get()
    }
}

pub fn verify() -> Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
