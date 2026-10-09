module examples::values::literal;

pub fn main() -> Int {
    42
}

pub fn verify() -> Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
