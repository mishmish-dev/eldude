module examples::ownership::traits;

trait Value {
    type Output;
    fn value(self) -> Self::Output;
}

struct Box<T> { item: T }

impl<T> Value for Box<T> {
    type Output = T;
    fn value(self) -> T {
        let Box { item } = self;
        item
    }
}

pub fn main() -> Int { Box { item: 42 }.value() }
