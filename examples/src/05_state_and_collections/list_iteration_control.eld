module list_iteration_control;

import collections::list::{List};
import state::ref::{Ref};
import eldude::fixture::{File, acquire};

effect Step {
    tail value(item: Int) -> Int;
}

effect Stop {
    affine stop() -> Unit;
}

fn first(values: List<Int>) -> Int {
    for item in values {
        if item == 5 {
            return item;
        };
    };
    0
}

pub fn main() -> Int {
    region local {
        let total: Ref<Int, @local> = Ref::new(0);
        handle {
            for item in [!Step::value(10), !Step::value(20), !Step::value(12)] {
                using (file = acquire()) {
                    total.set(total.get() + !Step::value(item));
                }
            };
        } with handler Step {
            value(item) => item;
            return result => result;
        };
        handle {
            for item in [1, 2, 3] {
                using (file = acquire()) {
                    !Stop::stop();
                    total.set(-1);
                }
            };
        } with handler Stop {
            stop() => ();
            return result => result;
        };
        total.get() + first([5, 6]) - 5
    }
}

pub fn verify() -> Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
