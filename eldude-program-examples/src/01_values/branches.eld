module examples::values::branches;

fn absolute(value: Int) -> Int {
    if value < 0 {
        -value
    } else {
        value
    }
}

pub fn main() -> Int {
    absolute(-7)
}

pub fn verify() -> Int {
    if main() == 7 {
        0
    } else {
        1
    }
}
