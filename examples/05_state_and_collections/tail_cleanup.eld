module examples::state_and_collections::tail_cleanup;

import core::cleanup::{Cleanup};
import state::ref::{Ref};

linear struct Guard<@r> {
    counter: Ref<Int, @r>
}

impl<@r> Cleanup<{state<@r>}> for Guard<@r> {
    fn cleanup(self) ->{state<@r>} Unit {
        let Guard { counter } = self;
        counter.replace(2);
    }
}

effect Read {
    tail value() -> Int;
}

pub fn main() -> Int {
    region local {
        let counter: Ref<Int, @local> = Ref::new(0);
        handle {
            let result = !Read::value();
            result + counter.get()
        } with handler Read {
            value() => {
                using (guard = Guard { counter }) {
                    // Return from the clause; clean up before the caller continues.
                    return 40;
                }
            }
        }
    }
}
