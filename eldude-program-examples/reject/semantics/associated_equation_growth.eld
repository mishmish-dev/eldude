module associated_equation_growth;

trait Output {
    type Item;
    fn read(view self) -> Int;
}

struct Box<T> {
    value: T
}

impl<T> Output for Box<T> {
    type Item = Box<Box<T>>::Item;
    fn read(view self) -> Int {
        42
    }
}

pub fn main() -> Int {
    42
}
