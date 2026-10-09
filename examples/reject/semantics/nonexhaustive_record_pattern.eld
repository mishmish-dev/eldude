module reject::nonexhaustive_record_pattern;

struct P {
    x: Bool,
    y: Int
}

pub fn main() -> Int {
    let point = P { x: false, y: 42 };
    match point {
        case P { y, x: true } => y;
    }
}
