module task_capture_rows;

import collections::dyn_array::{DynArray};

fn relay<
    @r,
    ..C
>(
    f: fn() ->{state<@r>} Int captures {..C}
) ->{suspend} fn() ->{state<@r>} Int captures {..C} where ..C: Discard {
    taskgroup {
        let task = spawn {
            f
        };
        await task
    }
}

pub fn main() ->{suspend} Int {
    region local {
        let values: DynArray<Int, @local> = DynArray::new();
        let f = fn() ->{state<@local>} Int captures {values} {
            let frozen = values.freeze();
            42
        };
        let g = relay(f);
        g()
    }
}

pub fn verify() ->{suspend} Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
