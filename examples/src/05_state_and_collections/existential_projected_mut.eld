module existential_projected_mut;

import collections::dyn_array::{DynArray};
import core::option::{Option};

trait Grow<@r> {
    fn grow(mut self, value: Int) ->{state<@r>} Unit;
    fn len(view self) ->{state<@r>} Nat;
}

impl<@r> Grow<@r> for DynArray<Int, @r> {
    fn grow(mut self, value: Int) ->{state<@r>} Unit {
        mut self.push(value);
    }
    fn len(view self) ->{state<@r>} Nat {
        view self.length()
    }
}

pub fn main() -> Int {
    region inner {
        region outer {
            let values: DynArray<Int, @inner> = DynArray::new();
            let item: any Grow<@inner> + Discard = values;
            let packages: DynArray<any Grow<@inner> + Discard, @outer> = DynArray::new();
            mut packages.push(item);
            let result = mut packages.withMut(
                0,
                fn(mut item: any Grow<@inner> + Discard) ->{state<@inner>} Int {
                    mut item.grow(42);
                    if view item.len() == 1nat {
                        42
                    } else {
                        0
                    }
                }
            );
            match result {
                case Option::Some(n) => n;
                case Option::None => 0;
            }
        }
    }
}

pub fn verify() -> Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
