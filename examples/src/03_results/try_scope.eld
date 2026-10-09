module examples::results::try_scope;

import core::result::{Result};

enum InputError {
    Missing
}

pub fn main() -> Int {
    let result: Result<InputError, Int> = try {
        let value: Result<InputError, Int> = Result::Err(InputError::Missing);
        value? + 1
    };
    match result {
        case Result::Ok(value) => value;
        case Result::Err(InputError::Missing) => 42;
    }
}

pub fn verify() -> Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
