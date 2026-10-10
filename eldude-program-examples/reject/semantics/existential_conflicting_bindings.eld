module existential_conflicting_bindings;

trait Read {
    type Item;
    fn read(view self) -> Self::Item;
}

struct A {}

impl Read for A {
    type Item = Int;
    fn read(view self) -> Int {
        42
    }
}

pub fn main() -> Int {
    let both: any Read<Item = Int> + Read<Item = Bool> + Discard = A {};
    view both.read()
}
