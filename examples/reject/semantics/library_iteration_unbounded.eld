module rejects::library_iteration_unbounded;

import core::iter::{Iterator, Next};

struct Repeat {}

impl Iterator for Repeat {
    type Item = Int;
    fn next(self) -> Next<Repeat, Int> {
        Next::Item(1, self)
    }
}

pub fn main() -> Int {
    let repeated = Repeat {};
    for _ in repeated {
        ();
    };
    42
}
