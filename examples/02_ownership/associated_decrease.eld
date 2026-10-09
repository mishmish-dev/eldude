module associated_decrease;

import collections::list::{List};
import core::result::{Result};

trait Flatten {
    type Item;
}

impl Flatten for Int {
    type Item = Int;
}

impl<T> Flatten for List<T> where T: Flatten {
    type Item = List<T::Item>;
}

fn answer(view values: List<Int>) -> List<Int>::Item where List<Int>: Flatten {
    [42]
}

pub fn main() -> Int {
    let values = [0];
    let result = answer(view values);
    match result.remove(0) {
        case Result::Ok((item, rest)) => item;
        case Result::Err((error, original)) => 0;
    }
}
