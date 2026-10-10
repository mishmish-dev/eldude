module projection_head;

trait Output {
    type Item;
}

trait Read {
    fn read(view self) -> Int;
}

struct A {}

impl Output for A {
    type Item = Int;
}

impl Read for A::Item {
    fn read(view self) -> Int {
        42
    }
}

pub fn main() -> Int {
    42
}
