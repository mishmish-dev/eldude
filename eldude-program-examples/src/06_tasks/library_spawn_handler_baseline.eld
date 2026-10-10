module library_spawn_handler_baseline;

import state::ref::{Ref};

effect Read {
    tail value() -> Int;
}

pub fn main() ->{suspend} Int {
    region local {
        let cell: Ref<Int, @local> = Ref::new(0);
        handle {
            taskgroup {
                handle {
                    spawn {
                        cell.replace(!Read::value());
                    };
                } with handler Read {
                    value() => 0;
                    return result => result;
                };
            };
            cell.get()
        } with handler Read {
            value() => 42;
            return result => result;
        }
    }
}

pub fn verify() ->{suspend} Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
