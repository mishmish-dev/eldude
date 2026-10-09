module list_api_values;

import collections::list::{List};
import core::option::{Option};
import core::result::{Result};

pub fn main() -> Int {
    let empty: List<Int> = List::new();
    let values = empty.push(10).push(20).push(30);
    let selected = values.filter(fn(view item: Int) -> Bool {
        item >= 20
    });
    let (small, large) = values.partition(fn(view item: Int) -> Bool {
        item < 20
    });
    let missing = (view values.get(-1) ?? 0) + (view values.get(3) ?? 0);
    match values.replace(1, 2) {
        case Result::Ok((old, updated)) => {
            old + (
                view updated.get(1) ?? 0
            ) + (
                view small.get(0) ?? 0
            ) + (
                view selected.get(0) ?? 0
            ) - (view large.get(0) ?? 0) + (view values.get(0) ?? 0) + missing
        };
        case Result::Err((error, original, replacement)) => 0;
    }
}

pub fn verify() -> Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
