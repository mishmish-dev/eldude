module existential_arguments;

import collections::list::{List};
import state::ref::{Ref};

trait Read<T> {
    fn read(view self, x: T) -> Int;
}

struct A {}

impl Read<Int> for A {
    fn read(view self, x: Int) -> Int {
        x
    }
}

impl Read<Bool> for A {
    fn read(view self, x: Bool) -> Int {
        if x {
            22
        } else {
            0
        }
    }
}

trait Kinds<T, F<_>, @r, !e, ..C, #N> {
    fn inspect(view self, values: F<T>, f: fn() ->{| e} Int captures {..C}) ->{| e} Int;
}

impl<@r> Kinds<Int, List, @r, {}, {@r}, 3> for A {
    fn inspect(view self, values: List<Int>, f: fn() -> Int captures {@r}) -> Int {
        f()
    }
}

pub fn main() -> Int {
    region local {
        let a: any Read<Int> + Discard = A {};
        let b: any Read<Bool> + Discard = A {};
        let kinds: any Kinds<Int, List, @local, {}, {@local}, 3> + Discard = A {};
        let cell: Ref<Int, @local> = Ref::new(0);
        let ignored = view kinds.inspect([0], fn() -> Int captures {cell} {
            let copy = cell;
            0
        });
        view a.read(20) + view b.read(true)
    }
}

pub fn verify() -> Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
