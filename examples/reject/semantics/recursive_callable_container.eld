module reject::recursive_callable_container;

struct Callback<T> {
    run: fn() -> T
}

enum Loop {
    Wrap(Callback<Loop>)
}

pub fn main() -> Int {
    42
}
