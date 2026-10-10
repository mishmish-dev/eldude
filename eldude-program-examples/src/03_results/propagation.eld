module examples::results::propagation;

import core::result::{Result};

enum InputError {
    Negative
}

fn nonnegative(value: Int) -> Result<Int, InputError> {
    if value < 0 {
        Result::Err(InputError::Negative)
    } else {
        Result::Ok(value)
    }
}

fn add(left: Int, right: Int) -> Result<Int, InputError> {
    Result::Ok(nonnegative(left)? + nonnegative(right)?)
}

pub fn main() -> Int {
    match add(19, 23) {
        case Result::Ok(value) => value;
        case Result::Err(_) => 0;
    }
}

pub fn verify() -> Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
