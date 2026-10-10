module examples::state_and_collections::list_failure;

import collections::list::{List};
import core::result::{Result};

pub fn main() -> Nat {
    let values = [10, 20, 30];
    match values.remove(99) {
        case Result::Ok((item, rest)) => view rest.length();
        case Result::Err((error, original)) => view original.length();
    }
}

pub fn verify() -> Int {
    if main() == 3nat {
        0
    } else {
        1
    }
}
