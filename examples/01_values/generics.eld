module examples::values::generics;

fn identity<T>(value: T) -> T { value }

pub fn main() -> Int {
    identity::<Int>(42)
}
