module reject::try_argument_temporary;

import core::result::{Result};
import eldude::fixture::{File, acquire, close};

fn consume(file: File, value: Unit) -> Unit {
    close(file);
}

pub fn main() -> Unit {
    let result: Result<Unit, Int> = try {
        let failed: Result<Unit, Int> = Result::Err(7);
        consume(acquire(), failed?)
    };
}
