module parameter_capture;

import state::ref::{Ref};

fn make<@r>(cell: Ref<Int, @r>) -> fn() ->{state<@r>} Int captures {cell} {
    fn() ->{state<@r>} Int captures {cell} {
        cell.get()
    }
}

fn nested<@r>(cell: Ref<Int, @r>) -> fn() ->{state<@r>} Int captures {cell} {
    make(cell)
}

pub fn main() -> Int {
    region local {
        let cell: Ref<Int, @local> = Ref::new(20);
        let first = nested(cell);
        let cell: Ref<Int, @local> = Ref::new(22);
        let second = nested(cell);
        first() + second()
    }
}
