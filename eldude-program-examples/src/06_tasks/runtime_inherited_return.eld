module examples::tasks::runtime_inherited_return;

import state::ref::{Ref};

effect Log {
    tail tick() -> Unit;
}

pub fn main() ->{suspend} Int {
    region r {
        let count: Ref<Int, @r> = Ref::new(40);
        handle {
            taskgroup {
                spawn {
                    if false {
                        !Log::tick();
                    }
                };
            };
        } with handler Log {
            tick() => ();
            return result => {
                count.replace(count.get() + 1);
                result
            }
        };
        count.get()
    }
}

pub fn verify() ->{suspend} Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
