module generic_projection;

trait Output<T> {
    type Item;
    fn read(view self) -> Int;
}

struct A {}

impl Output<Int> for A {
    type Item = Int;
    fn read(view self) -> Int {
        42
    }
}

fn answer<T>(view item: T) -> T::Item where T: Output<Int>, T::Item = Int {
    42
}

pub fn main() -> Int {
    let item = A {};
    answer(view item)
}
