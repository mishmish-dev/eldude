module examples::values::arithmetic;

pub fn main() -> Int {
    2 + 3 * 4
}

pub fn verify() -> Int {
    if main() == 14 {
        0
    } else {
        1
    }
}
