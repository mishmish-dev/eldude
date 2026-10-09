module mut_exit_paths;

import collections::dyn_array::{DynArray};
import core::option::{Option};
import core::result::{Result};

effect Stop {
    affine stop() -> Unit;
}

fn early<@r>(mut values: DynArray<Int, @r>) ->{state<@r>} Unit {
    mut values.push(1);
    return();
}

fn failed<@r>(mut values: DynArray<Int, @r>) ->{state<@r>} Result<Unit, Unit> {
    mut values.push(2);
    Result::Err(())?;
    Result::Ok(())
}

fn stopped<@r>(mut values: DynArray<Int, @r>) ->{Stop, state<@r>} Unit {
    mut values.push(3);
    !Stop::stop();
    mut values.push(0);
}

pub fn main() -> Int {
    region local {
        let values: DynArray<Int, @local> = DynArray::new();
        early(mut values);
        failed(mut values);
        handle {
            stopped(mut values)
        } with handler Stop {
            stop() => ();
            return x => x;
        };
        mut values.push(42);
        if view values.length() == 4nat {
            match mut values.pop() {
                case Option::Some(n) => n;
                case Option::None => 0;
            }
        } else {
            0
        }
    }
}
