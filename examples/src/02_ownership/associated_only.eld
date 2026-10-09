module associated_only;

trait Output {
    type Item;
}

struct Box<T> {
    value: T
}

impl Output for Box<Int> {
    type Item = Int;
}

fn answer(view box: Box<Int>) -> Box<Int>::Item {
    42
}

pub fn main() -> Int {
    let box = Box { value: 0 };
    answer(view box)
}

pub fn verify() -> Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
