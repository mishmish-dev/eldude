module tooling_tests;

pub fn main() -> Int {
    if 6 * 7 == 42 {
        0
    } else {
        1
    }
}

pub fn verify() -> Int {
    if main() == 0 {
        0
    } else {
        1
    }
}
