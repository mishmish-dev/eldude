module examples::results::try_scope;

import core::result::{Result};

enum InputError {
    Missing
}

struct Answer {
    number: Int,
}

pub fn main() -> Int {
    let successful = try {
        let value: Result<Bool, InputError> = Result::Ok(true);
        value?
    };
    let mapped: Result<Int, Unit> = successful.map(
        fn(flag: Bool) -> Int {
            if flag {
                40
            } else {
                0
            }
        }
    ).mapError(fn(error: InputError) -> Unit {
        ()
    });
    let chained: Result<Int, Unit> = mapped.andThen(
        fn(value: Int) -> Result<Int, Unit> {
            Result::Ok(value + 2)
        }
    );
    let wrapped: Result<Answer, Unit> = try {
        Answer { number: chained? }
    };
    let result: Result<Int, InputError> = try {
        let value: Result<Int, InputError> = Result::Err(InputError::Missing);
        value? + 1
    };
    match result {
        case Result::Ok(value) => value;
        case Result::Err(InputError::Missing) => match wrapped {
            case Result::Ok(answer) => answer.number;
            case Result::Err(_) => 0;
        };
    }
}

pub fn verify() -> Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
