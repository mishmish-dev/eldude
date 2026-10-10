module reject::try_argument_temporary;

import core::result::{Result};
import eldude::fixture::{File, acquire, close};

fn consume(file: File, value: Unit) -> Unit {
    close(file);
}

pub fn main() -> Unit {
    let result: Result<Int, Unit> = try {
        let failed: Result<Int, Unit> = Result::Err(7);
        consume(acquire(), failed?)
    };
}
