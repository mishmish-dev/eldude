module examples::results::option;

import core::option::{Option};

pub fn main() -> Int {
    let present = Option::Some(40);
    present.map(fn(value: Int) => value + 2) ?? 0
}
