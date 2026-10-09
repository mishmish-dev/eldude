module rejects::library_iteration_recursive_step;

import core::iter::{Iterator, Next};

enum Reentrant {
    Done,
    More(Reentrant)
}

impl Iterator for Reentrant {
    type Item = Int;
    fn next(self) -> Next<Reentrant, Int> {
        match self {
            case Reentrant::Done => {
                for _ in self {
                    ();
                };
                Next::Done
            };
            case Reentrant::More(rest) => {
                rest.next();
                Next::Done
            };
        }
    }
}

pub fn main() -> Int {
    42
}
