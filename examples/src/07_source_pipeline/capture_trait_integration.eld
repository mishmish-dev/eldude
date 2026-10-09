module capture_trait_integration;

import collections::dyn_array::{DynArray};
import eldude::fixture::{File, acquire, close};

fn relay<..C>(f: fn() -> Int captures {..C}) -> fn() -> Int captures {..C} {
    f
}

fn relayPair<..C>(f: fn() -> Int captures {..C}) -> (fn() -> Int captures {..C}, Int) {
    (relay(f), 0)
}

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

trait Peek<T, @r> where T: Dup {
    type Item;
    fn peek(view self) ->{state<@r>} Self::Item where Self: Discard;
}

impl<@r> Peek<Int, @r> for DynArray<Int, @r> {
    type Item = Int;
    fn peek(view self) ->{state<@r>} Int {
        if view self.length() == 1nat {
            42
        } else {
            0
        }
    }
}

pub fn main() -> Int {
    region local {
        let file = acquire();
        let (done, ignored) = relayPair(fn() -> Int captures {file} {
            close(file);
            0
        });
        let values: DynArray<Int, @local> = DynArray::new();
        let item: any Grow<@local> + Peek<Int, @local, Item = Int> + Discard = values;
        mut item.grow(42);
        let observed = view item.peek();
        observed + done()
    }
}

pub fn verify() -> Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
