module library_owned_combinators;

import core::option::{Option};
import core::result::{Result};
import eldude::fixture::{File, acquire, close};

pub fn main() -> Int {
    let present = Option::Some(acquire());
    let flag = view present.isSome();
    let mapped = present.map(
        fn(file: File) -> Result<Int, File> {
            Result::Ok(file)
        }
    ).andThen(
        fn(result: Result<Int, File>) -> Option<File> {
            match result {
                case Result::Err(_) => Option::None;
                case Result::Ok(file) => Option::Some(file);
            }
        }
    );
    match mapped {
        case Option::Some(file) => close(file);
        case Option::None => ();
    };
    let failed: Result<File, Int> = Result::Err(acquire());
    match failed.map(fn(n: Int) -> Int {
        n + 1
    }) {
        case Result::Err(file) => close(file);
        case Result::Ok(_) => ();
    };
    let succeeded: Result<Int, File> = Result::Ok(acquire());
    let result = succeeded.mapError(
        fn(n: Int) -> Int {
            n + 1
        }
    ).andThen(fn(file: File) -> Result<Int, Int> {
        close(file);
        Result::Ok(42)
    });
    match result {
        case Result::Ok(n) => if flag {
            n
        } else {
            0
        };
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
