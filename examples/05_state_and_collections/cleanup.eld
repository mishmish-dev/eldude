module examples::state_and_collections::cleanup;

import core::cleanup::{Cleanup};
import state::ref::{Ref};

linear struct Guard<@r> { counter: Ref<Int, @r> }

impl<@r> Cleanup<{state<@r>}> for Guard<@r> {
    fn cleanup(self) ->{state<@r>} Unit {
        let Guard { counter } = self;
        counter.replace(counter.get() + 1);
    }
}

pub fn main() -> Int {
    region local {
        let counter: Ref<Int, @local> = Ref::new(0);
        using (guard = Guard { counter }) { () };
        counter.get()
    }
}
