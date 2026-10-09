module capture_free_erasure;

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
        let hidden: any Read + CaptureFree + Dup + Discard = Number { value: 42 };
        let cell: Ref<any Read + CaptureFree + Dup + Discard, @local> = Ref::new(hidden);
        let copy = cell.get();
        view copy.read()
    }
}

pub fn verify() -> Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
