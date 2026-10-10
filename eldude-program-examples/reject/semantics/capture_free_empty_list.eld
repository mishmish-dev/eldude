module capture_free_empty_list;

import state::ref::{Ref};
import collections::list::{List};

pub fn main() -> Int {
    region local {
        let empty: List<Ref<Int, @local>> = List::new();
        let cell: Ref<List<Ref<Int, @local>>, @local> = Ref::new(empty);
        0
    }
}
