module list_api_empty;

import collections::list::{List};
import core::result::{Result};
import eldude::fixture::{acquire, close};

pub fn main() -> Int {
    let empty: List<Int> = [];
    empty.filter(fn(view item: Int) -> Bool {
        1 / 0 == item
    });
    empty.partition(fn(view item: Int) -> Bool {
        1 / 0 == item
    });
    view empty.with(0, fn(view item: Int) -> Int {
        1 / 0
    });
    match [].replace(0, acquire()) {
        case Result::Err((error, original, replacement)) => {
            close(replacement);
            for file in original {
                close(file);
            };
            if error.length == 0nat {
                42
            } else {
                0
            }
        };
        case Result::Ok((old, updated)) => {
            close(old);
            for file in updated {
                close(file);
            };
            0
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
