module list_api_generic_with;

import collections::list::{List};
import core::option::{Option};
import state::ref::{Ref};

fn inspect<
    T,
    R,
    !e,
    ..C
>(
    view values: List<T>,
    callback: fn(view T) ->{| e} R captures {..C},
) ->{| e} Option<R> where ..C: Discard {
    view values.with(0, callback)
}

pub fn main() -> Int {
    region local {
        let calls: Ref<Int, @local> = Ref::new(0);
        let values = [41];
        let found = inspect(
            view values,
            fn(view item: Int) ->{state<@local>} Int captures {calls} {
                calls.replace(calls.get() + 1);
                item
            }
        );
        (found ?? 0) + calls.get()
    }
}

pub fn verify() -> Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
