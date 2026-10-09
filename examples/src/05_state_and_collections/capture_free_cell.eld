module capture_free_cell;

import state::ref::{Ref};
import collections::list::{List};

fn store<T, @r>(cell: Ref<T, @r>, value: T) ->{state<@r>} Unit where T: CaptureFree + Discard {
    cell.set(value);
}

struct Pair {
    left: Int,
    right: Int
}

enum Choice {
    Empty,
    Pair(Pair)
}

pub fn main() -> Int {
    region local {
        let cell: Ref<Int, @local> = Ref::new(0);
        let alias = cell;
        store(alias, 40);
        let pairs: Ref<List<Choice>, @local> = Ref::new([Choice::Empty]);
        pairs.set([Choice::Pair(Pair { left: 20, right: 22 })]);
        let closed: fn() -> Int captures {} = fn() -> Int {
            2
        };
        let callback: Ref<fn() -> Int captures {}, @local> = Ref::new(closed);
        let increment = Ref::new(0);
        increment.set(callback.get()());
        cell.get() + increment.get()
    }
}

pub fn verify() -> Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
