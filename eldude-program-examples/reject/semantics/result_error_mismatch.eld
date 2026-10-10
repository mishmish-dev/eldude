module result_error_mismatch;

import core::result::{Result};

enum FirstError {
    Missing
}

enum SecondError {
    Missing
}

fn attempt() -> Result<Int, SecondError> {
    let value: Result<Int, FirstError> = Result::Err(FirstError::Missing);
    Result::Ok(value?)
}

pub fn main() -> Int {
    42
}
