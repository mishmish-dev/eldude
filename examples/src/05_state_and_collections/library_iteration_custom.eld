module examples::collections::library_iteration_custom;

import core::iter::{Iterator, Next};
import state::ref::{Ref};

enum Steps {
    Done,
    More(Int, Steps)
}

impl Iterator for Steps {
    type Item = Int;
    fn next(self) -> Next<Steps, Int> {
        match self {
            case Steps::Done => Next::Done;
            case Steps::More(item, rest) => Next::Item(item, rest);
        }
    }
}

pub fn main() ->{diverge} Int {
    region r {
        let total: Ref<Int, @r> = Ref::new(0);
        for item in Steps::More(19, Steps::More(23, Steps::Done)) {
            total.set(total.get() + item);
        };
        total.get()
    }
}

pub fn verify() ->{diverge} Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
