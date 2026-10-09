module reject::propagate_argument_temporary;

import core::result::{Result};
import eldude::fixture::{File, acquire, close};

fn consume(file: File, value: Unit) -> Unit {
    close(file);
}

fn attempt() -> Result<Int, Unit> {
    let failed: Result<Int, Unit> = Result::Err(7);
    Result::Ok(consume(acquire(), failed?))
}

pub fn main() -> Unit {
    attempt();
}
