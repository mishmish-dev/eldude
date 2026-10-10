module list_api_filter_effect;

import collections::list::{List};
import state::ref::{Ref};

pub fn main() -> Int {
    region local {
        let count: Ref<Int, @local> = Ref::new(0);
        [1].filter(fn(view item: Int) ->{state<@local>} Bool {
            count.replace(item);
            true
        });
        42
    }
}
