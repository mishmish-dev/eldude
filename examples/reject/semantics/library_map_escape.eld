module library_map_escape;

import core::option::{Option};
import state::ref::{Ref};

trait Read {
    fn read(view self) -> Int;
}

struct Held<@r> {
    cell: Ref<Int, @r>
}

impl<@r> Read for Held<@r> {
    fn read(view self) -> Int {
        42
    }
}

pub fn main() -> Int {
    let escaped = region local {
        let cell: Ref<Int, @local> = Ref::new(42);
        Option::Some(0).map(
            fn(n: Int) -> any Read + Discard captures {cell} {
                let hidden: any Read + Discard = Held { cell };
                hidden
            }
        )
    };
    0
}
