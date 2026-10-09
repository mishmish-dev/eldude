module list_api_with_escape;

import collections::list::{List};
import state::ref::{Ref};

pub fn main() -> Int {
    let escaped = region local {
        let cell: Ref<Int, @local> = Ref::new(42);
        let values = [cell];
        view values.with(0, fn(view item: Ref<Int, @local>) -> Ref<Int, @local> {
            item
        })
    };
    42
}
