module existential_mut_branch_escape;

import collections::dyn_array::{DynArray};
import state::ref::{Ref};

trait Read {
    fn read(view self) -> Int;
}

struct Holder<@r> {
    cell: Ref<Int, @r>
}

impl<@r> Read for Holder<@r> {
    fn read(view self) -> Int {
        42
    }
}

trait Store<@r> {
    fn store(mut self, value: any Read + Discard) ->{state<@r>} Unit;
    fn len(view self) ->{state<@r>} Nat;
}

impl<@r> Store<@r> for DynArray<any Read + Discard, @r> {
    fn store(mut self, value: any Read + Discard) ->{state<@r>} Unit {
        mut self.push(value);
    }
    fn len(view self) ->{state<@r>} Nat {
        view self.length()
    }
}

pub fn main() -> Nat {
    region outer {
        let values: DynArray<any Read + Discard, @outer> = DynArray::new();
        let owner: any Store<@outer> + Discard = values;
        region inner {
            let cell: Ref<Int, @inner> = Ref::new(0);
            let item: any Read + Discard = Holder { cell: cell };
            if true {
                mut owner.store(item);
            } else {
                mut owner.store(item);
            };
        };
        view owner.len()
    }
}
