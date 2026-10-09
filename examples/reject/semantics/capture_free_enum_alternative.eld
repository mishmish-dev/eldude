module capture_free_enum_alternative;

import state::ref::{Ref};

enum Choice<@r> {
    Empty,
    Scoped(Ref<Int, @r>)
}

pub fn main() -> Int {
    region local {
        let cell: Ref<Choice<@local>, @local> = Ref::new(Choice::Empty);
        0
    }
}
