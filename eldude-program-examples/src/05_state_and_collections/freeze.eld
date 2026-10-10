module examples::state_and_collections::freeze;

import collections::dyn_array::{DynArray};
import collections::list::{List};

fn freezeBuffer<T, @r>(buffer: DynArray<T, @r>) ->{state<@r>} List<T> {
    buffer.freeze()
}

pub fn main() -> Nat {
    let values = region local {
        let buffer: DynArray<Int, @local> = DynArray::new();
        mut buffer.push(19);
        mut buffer.push(23);
        // List<Int> is capture-free, including through a generic wrapper.
        freezeBuffer(buffer)
    };
    view values.length()
}

pub fn verify() -> Int {
    if main() == 2nat {
        0
    } else {
        1
    }
}
