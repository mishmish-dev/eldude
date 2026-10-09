module mut_suspension;

import collections::dyn_array::{DynArray};

effect Pause {
    tail pause() -> Unit;
}

fn update<@r>(mut values: DynArray<Int, @r>) ->{Pause, state<@r>} Int {
    !Pause::pause();
    mut values.push(42);
    42
}

pub fn main() -> Int {
    region local {
        let values: DynArray<Int, @local> = DynArray::new();
        let answer = handle {
            update(mut values)
        } with handler Pause {
            pause() => ();
            return x => x;
        };
        let length = view values.length();
        if length == 1nat {
            answer
        } else {
            0
        }
    }
}
