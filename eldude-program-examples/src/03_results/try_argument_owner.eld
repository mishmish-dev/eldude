module examples::results::try_argument_owner;

import core::result::{Result};
import eldude::fixture::{File, acquire, close};

fn consume(file: File, result: Result<Int, Int>) -> Int {
    close(file);
    match result {
        case Result::Ok(value) => value;
        case Result::Err(error) => error;
    }
}

pub fn main() -> Int {
    consume(acquire(), try {
        let failed: Result<Int, Int> = Result::Err(42);
        failed?
    })
}

pub fn verify() -> Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
