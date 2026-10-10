module examples::tasks::runtime_cancel_shutdown;

import task::{yield};
import eldude::fixture::{acquire};
import state::ref::{Ref};

pub fn main() ->{suspend} Int {
    region r {
        let count: Ref<Int, @r> = Ref::new(0);
        taskgroup {
            let child = spawn {
                using (outer = acquire()) {
                    taskgroup {
                        spawn {
                            using (inner = acquire()) {
                                yield();
                                count.replace(42);
                            }
                        };
                    };
                    count.replace(0);
                }
            };
            spawn {
                child.cancel();
            };
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
