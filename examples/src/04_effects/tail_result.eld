module examples::effects::tail_result;

import core::result::{Result};

enum ReadError {
    Unavailable
}

fn unavailable() -> Result<ReadError, Int> {
    Result::Err(ReadError::Unavailable)
}

effect Read {
    tail value() -> Result<ReadError, Int>;
}

pub fn main() -> Int {
    handle {
        match !Read::value() {
            case Result::Ok(value) => value;
            case Result::Err(_) => 42;
        }
    } with handler Read {
        value() => {
            // Err becomes the operation result and reaches the caller's match.
            let value = unavailable()?;
            Result::Ok(value)
        }
    }
}

pub fn verify() -> Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
