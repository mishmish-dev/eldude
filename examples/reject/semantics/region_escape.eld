module examples::reject::region_escape;

import state::ref::{Ref};

fn main() -> Int {
    let escaped = region local {
        let cell: Ref<Int, @local> = Ref::new(42);
        fn() => cell.get()
    };
    escaped()
}
