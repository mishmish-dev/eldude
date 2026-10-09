module examples::values::tuples;

pub fn main() -> Int {
    let (left, right) = (19, 23);
    left + right
}

pub fn verify() -> Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
