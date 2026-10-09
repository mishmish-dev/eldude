module existential_mut;

import collections::dyn_array::{DynArray};

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

fn relay<@r>(item: any Grow<@r> + Discard) -> any Grow<@r> + Discard {
    match item {
        case value => value;
    }
}

fn make<@r>(flag: Bool) ->{state<@r>} any Grow<@r> + Discard {
    if flag {
        let values: DynArray<Int, @r> = DynArray::new();
        let item: any Grow<@r> + Discard = values;
        return item;
    } else {
        let values: DynArray<Int, @r> = DynArray::new();
        let item: any Grow<@r> + Discard = values;
        item
    }
}

pub fn main() -> Nat {
    region local {
        let item = relay(make::<@local>(true));
        mut item.grow(42);
        view item.len()
    }
}
