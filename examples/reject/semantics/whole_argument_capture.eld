module examples::reject::whole_argument_capture;

import state::ref::{Ref};

trait Read {
    fn read(view self) -> Int;
}

struct Value {
    number: Int,
}

impl Read for Value {
    fn read(view self) -> Int { self.number }
}

fn first<@r>(pair: (any Read + Discard, Ref<Int, @r>)) -> any Read + Discard {
    let (value, _) = pair;
    value
}

fn main() -> Int {
    let escaped = region local {
        let value: any Read + Discard = Value { number: 42 };
        let cell: Ref<Int, @local> = Ref::new(0);
        // first's public bound retains the whole pair, including @local.
        first((value, cell))
    };
    view escaped.read()
}
