module trait_stronger_method;

trait Read {
    fn read(view self) -> Int;
}

struct Box<T> {
    item: T
}

impl<T> Read for Box<T> {
    fn read(view self) -> Int where T: Dup {
        42
    }
}

pub fn main() -> Int {
    42
}
