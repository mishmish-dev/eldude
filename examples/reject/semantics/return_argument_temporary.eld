module reject::return_argument_temporary;

import eldude::fixture::{File, acquire, close};

fn consume(file: File, value: Unit) -> Unit {
    close(file);
}

pub fn main() -> Unit {
    consume(acquire(), return())
}
