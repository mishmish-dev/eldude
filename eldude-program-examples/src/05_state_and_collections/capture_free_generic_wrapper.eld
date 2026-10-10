module examples::collections::capture_free_generic_wrapper;

import state::ref::{Ref};

struct Holder<T, @r> where T: CaptureFree + Discard {
    cell: Ref<T, @r>
}

enum Wrapped<T, @r> where T: CaptureFree + Discard {
    Cell(Ref<T, @r>)
}

pub fn main() -> Int {
    region local {
        let cell: Ref<Int, @local> = Ref::new(42);
        let holder = Holder { cell };
        holder.cell.get()
    }
}

pub fn verify() -> Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
