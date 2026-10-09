module associated_alias_cycle;

trait Output {
    type First;
    type Second;
}

struct A {}

impl Output for A {
    type First = Self::Second;
    type Second = Self::First;
}

pub fn main() -> Int {
    42
}
