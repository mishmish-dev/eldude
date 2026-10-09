module trait_overlap;

trait Read {
    fn read(view self) -> Int;
}

struct Box<T> {
    item: T
}

impl<T> Read for Box<T> where T: Dup {
    fn read(view self) -> Int {
        42
    }
}

impl Read for Box<Int> where Int: Discard {
    fn read(view self) -> Int {
        42
    }
}

pub fn main() -> Int {
    42
}
