module list_api_replace_owned;

import collections::list::{List};
import core::result::{Result};
import eldude::fixture::{File, acquire, close};

pub fn main() -> Int {
    let values: List<File> = [acquire(), acquire()];
    match values.replace(-1, acquire()) {
        case Result::Ok((old, updated)) => {
            close(old);
            for file in updated {
                close(file);
            };
            0
        };
        case Result::Err((error, original, replacement)) => {
            close(replacement);
            for file in original {
                close(file);
            };
            if error.index == -1 {
                if error.length == 2nat {
                    42
                } else {
                    0
                }
            } else {
                0
            }
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
