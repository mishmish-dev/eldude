module reject::private_record_constructor;

import examples::values::member_visibility_facade::{Wrapped, Point, Opaque, Status, make, status};

pub fn main() -> Int {
    Wrapped { x: 42 };
    42
}
