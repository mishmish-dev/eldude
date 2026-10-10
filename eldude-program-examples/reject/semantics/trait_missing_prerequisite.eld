module trait_missing_prerequisite;

trait Read {
    fn read(view self) -> Int;
}

trait Answer {
    fn answer(view self) -> Int;
}

struct Leaf {}

struct Wrapper<T> {
    item: T
}

impl<T> Answer for Wrapper<T> where T: Read {
    fn answer(view self) -> Int {
        42
    }
}

pub fn main() -> Int {
    let item = Wrapper { item: Leaf {} };
    view item.answer()
}
