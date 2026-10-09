module reject::recursive_callable_group;

enum Left {
    Wrap(Right)
}

enum Right {
    Wrap(fn(Left) -> Int)
}

pub fn main() -> Int {
    42
}
