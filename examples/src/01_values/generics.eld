module examples::values::generics;

fn identity<T>(value: T) -> T {
    value
}

pub fn main() -> Int {
    identity::<Int>(42)
}

pub fn verify() -> Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
