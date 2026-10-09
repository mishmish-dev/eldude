module list_api_next;

import collections::list::{List};
import core::iter::{Iterator, Next};

fn step<T>(values: List<T>) -> Next<List<T>, T> {
    values.next()
}

pub fn main() -> Int {
    let values = [20, 22];
    match step(values) {
        case Next::Done => 0;
        case Next::Item(first, tail) => match tail.next() {
            case Next::Done => 0;
            case Next::Item(second, rest) => match rest.next() {
                case Next::Done => first + second;
                case Next::Item(extra, remaining) => 0;
            };
        };
    }
}

pub fn verify() -> Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
