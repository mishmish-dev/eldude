module examples::reject::freeze_captured_elements;

import collections::dyn_array::{DynArray};
import state::ref::{Ref};

// Deliberately conservative: even outer-scope references prevent the frozen
// result from shedding the inner owner's region dependency.
fn main() -> Nat {
    region outer {
        let cell: Ref<Int, @outer> = Ref::new(42);
        let values = region inner {
            let buffer: DynArray<Ref<Int, @outer>, @inner> = DynArray::new();
            mut buffer.push(cell);
            buffer.freeze()
        };
        view values.length()
    }
}
