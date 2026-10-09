module reject::recursive_callable_alias;

type Callback<T> = fn(T) -> Int;

enum Loop {
    Wrap(Callback<Loop>)
}

pub fn main() -> Int {
    42
}
