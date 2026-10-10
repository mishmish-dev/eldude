module reject::recursive_callable_parameter;

enum Loop {
    Wrap(fn(Loop) -> Int)
}

pub fn main() -> Int {
    42
}
