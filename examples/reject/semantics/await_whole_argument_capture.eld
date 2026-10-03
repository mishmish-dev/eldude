module examples::reject::await_whole_argument_capture;

import state::ref::{Ref};
import task::{Task};

trait Read {
    fn read(view self) -> Int;
}

struct Value {
    number: Int,
}

impl Read for Value {
    fn read(view self) -> Int { self.number }
}

fn first<@r>(
    pair: (Task<any Read + Discard>, Ref<Int, @r>),
) -> Task<any Read + Discard> {
    let (task, _) = pair;
    task
}

fn main() ->{suspend, diverge} Int {
    taskgroup {
        let value: any Read + Discard = Value { number: 42 };
        let task = spawn value;
        let escaped = region local {
            let cell: Ref<Int, @local> = Ref::new(0);
            let forwarded = first((task, cell));
            // Await must preserve first's conservative dependency on @local.
            await forwarded
        };
        view escaped.read()
    }
}
