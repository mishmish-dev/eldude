module generic_kinds;

import collections::list::{List};

fn answer<#N>() -> Int {
    42
}

fn inspect<F<_>>(view values: F<Int>) -> Int {
    0
}

pub fn main() -> Int {
    let values = [0];
    inspect::<List>(view values) + answer::<3>()
}
