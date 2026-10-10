module examples::tasks::runtime_cancel_await;

import task::{yield};
import eldude::fixture::{acquire};
import state::ref::{Ref};

pub fn main() ->{suspend} Int {
    region r {
        let count: Ref<Int, @r> = Ref::new(42);
        taskgroup {
            let child = spawn {
                using (outer = acquire()) {
                    taskgroup {
                        let work = spawn {
                            using (inner = acquire()) {
                                yield();
                                yield();
                                count.replace(0);
                            }
                        };
                        await work;
                    }
                }
            };
            spawn {
                yield();
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
