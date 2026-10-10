module reject::private_enum_pattern;

import examples::values::member_visibility_facade::{Wrapped, Point, Opaque, Status, make, status};

pub fn main() -> Int {
    match status() {
        case Status::Hidden(x) => x;
        case _ => 0;
    }
}
