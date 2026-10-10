module result_try_error_mismatch;

import core::result::{Result};

enum FirstError {
    Missing
}

enum SecondError {
    Missing
}

pub fn main() -> Int {
    let result: Result<Int, SecondError> = try {
        let value: Result<Int, FirstError> = Result::Err(FirstError::Missing);
        value?
    };
    42
}
