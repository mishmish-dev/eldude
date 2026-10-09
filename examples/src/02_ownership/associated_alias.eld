module associated_alias;

trait Output {
    type First;
    type Second;
}

struct A {}

impl Output for A {
    type First = Int;
    type Second = Self::First;
}

fn answer(view item: A) -> A::Second {
    42
}

pub fn main() -> Int {
    let item = A {};
    answer(view item)
}

pub fn verify() -> Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
