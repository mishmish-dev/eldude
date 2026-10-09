module reject::private_enum_constructor;

import examples::values::member_visibility_facade::{Wrapped, Point, Opaque, Status, make, status};

pub fn main() -> Int {
    Status::Hidden(42);
    42
}
