module parameter_capture_escape;

import state::ref::{Ref};

fn make<@r>(cell: Ref<Int, @r>) -> fn() ->{state<@r>} Int captures {cell} {
    fn() {
        cell.get()
    }
}

pub fn main() -> Int {
    let escaped = region local {
        let cell: Ref<Int, @local> = Ref::new(42);
        make(cell)
    };
    escaped()
}
