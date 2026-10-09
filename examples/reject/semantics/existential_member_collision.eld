module existential_member_collision;

trait First {
    fn read(view self) -> Int;
}

trait Second {
    fn read(view self) -> Int;
}

struct A {}

impl First for A {
    fn read(view self) -> Int {
        20
    }
}

impl Second for A {
    fn read(view self) -> Int {
        22
    }
}

pub fn main() -> Int {
    let both: any First + Second + Discard = A {};
    view both.read()
}
