module reject::list_new_arity;

import collections::list::{List};

pub fn main() -> Int {
    let values: List<Int> = List::new(unknownName);
    view values.length();
    42
}
