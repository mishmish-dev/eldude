module examples::tasks::cleanup_mask_pending;

import eldude::fixture::{yield};
import core::cleanup::{Cleanup};
import state::ref::{Ref};

linear struct Guard<@r> {
    counter: Ref<Int, @r>
}

impl<@r> Cleanup<{suspend, state<@r>}> for Guard<@r> {
    fn cleanup(self) ->{suspend, state<@r>} Unit {
        let Guard { counter } = self;
        yield();
        counter.replace(42);
        yield();
    }
}

pub fn main() ->{suspend} Int {
    region local {
        let counter: Ref<Int, @local> = Ref::new(0);
        taskgroup {
            let child = spawn {
                using (guard = Guard { counter }) {
                    ()
                };
                yield();
                counter.replace(0);
            };
            spawn {
                child.cancel();
            };
        };
        counter.get()
    }
}

pub fn verify() ->{suspend} Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
