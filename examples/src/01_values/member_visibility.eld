module examples::values::member_visibility;

import examples::values::member_visibility_facade::{Point, Status, make, status};

pub fn main() -> Int {
    let s = make();
    let p = Point { x: view s.value() };
    let Point { x } = p;
    let named = Status::Named { value: x };
    let n = match named {
        case Status::Named { value } => value;
        case _ => 0;
    };
    match status() {
        case Status::Ready(_) => 0;
        case _ => n;
    }
}

pub fn verify() -> Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
