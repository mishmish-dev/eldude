module reject::private_enum_remainder;

import examples::values::member_visibility_facade::{Wrapped, Point, Opaque, Status, make, status};

pub fn main() -> Int {
    match status() {
        case Status::Ready(x) => x;
        case Status::Named { value } => value;
    }
}
