module reject::recursive_callable_result;

enum Loop {
    Wrap(fn() -> Loop)
}

pub fn main() -> Int {
    42
}
