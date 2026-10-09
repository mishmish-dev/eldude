module capture_free_erased;

import state::ref::{Ref};

trait Read {
    fn read(view self) -> Int;
}

struct Number {
    value: Int
}

impl Read for Number {
    fn read(view self) -> Int {
        self.value
    }
}

pub fn main() -> Int {
    region local {
        let hidden: any Read + Discard = Number { value: 42 };
        let cell: Ref<any Read + Discard, @local> = Ref::new(hidden);
        0
    }
}
