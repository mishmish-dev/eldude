module mut_alias_conflict;

import collections::dyn_array::{DynArray};

fn both<@r>(mut a: DynArray<Int, @r>, view b: DynArray<Int, @r>) -> Unit {}

pub fn main() -> Int {
    region local {
        let values: DynArray<Int, @local> = DynArray::new();
        both(mut values, view values);
        42
    }
}
