module examples::results::runtime_cleanup_propagation;

import core::cleanup::{Cleanup};
import core::result::{Result};
import state::ref::{Ref};
import task::{yield};

linear struct Guard<@r> {
    count: Ref<Int, @r>
}

impl<@r> Cleanup<{state<@r>, suspend}> for Guard<@r> {
    fn cleanup(self) ->{state<@r>, suspend} Unit {
        let Guard { count } = self;
        yield();
        count.replace(count.get() + 1);
    }
}

fn descend<@r>(n: Int, count: Ref<Int, @r>) ->{state<@r>, suspend, diverge} Result<Int, Int> {
    using (guard = Guard { count }) {
        if n == 0 {
            return Result::Err(7);
        };
        let result = descend(n - 1, count)?;
        Result::Ok(result)
    }
}

pub fn main() ->{suspend, diverge} Int {
    region r {
        let count: Ref<Int, @r> = Ref::new(0);
        let result = descend(2048, count);
        if count.get() == 2049 {
            match result {
                case Result::Err(error) => error + 35;
                case Result::Ok(_) => 0;
            }
        } else {
            0
        }
    }
}

pub fn verify() ->{suspend, diverge} Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
