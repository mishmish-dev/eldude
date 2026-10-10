module existential_mut_nonowner;

trait Grow {
    fn grow(mut self) -> Unit;
}

struct A {}

impl Grow for A {
    fn grow(mut self) -> Unit {}
}

pub fn main() -> Int {
    let item: any Grow + Discard = A {};
    mut item.grow();
    42
}
