module generic_constructor_as_type;

import collections::list::{List};

fn answer<T>() -> Int {
    42
}

pub fn main() -> Int {
    answer::<List>()
}
