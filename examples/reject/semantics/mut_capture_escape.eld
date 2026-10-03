module examples::reject::mut_capture_escape;

import collections::dyn_array::{DynArray};
import state::ref::{Ref};

trait Read {
    fn read(view self) -> Int;
}

struct Holder<@r> {
    cell: Ref<Int, @r>,
}

impl<@r> Read for Holder<@r> {
    fn read(view self) -> Int { 42 }
}

fn append<@r>(
    mut buffer: DynArray<any Read + Discard, @r>,
    value: any Read + Discard,
) ->{state<@r>} Unit {
    mut buffer.push(value);
}

fn main() -> Nat {
    region outer {
        let buffer: DynArray<any Read + Discard, @outer> = DynArray::new();
        region inner {
            let cell: Ref<Int, @inner> = Ref::new(0);
            let value: any Read + Discard = Holder { cell: cell };
            // Unit cannot hide the inner capture retained by the outer owner.
            append(mut buffer, value);
        };
        view buffer.length()
    }
}
