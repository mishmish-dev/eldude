module examples::values::startup;

let base = 40;

let answer = addTwo(base);

fn addTwo(value: Int) -> Int {
    value + 2
}

pub fn main() -> Int {
    answer
}

pub fn verify() -> Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
