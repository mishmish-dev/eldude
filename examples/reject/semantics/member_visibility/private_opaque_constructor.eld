module reject::private_opaque_constructor;

import examples::values::member_visibility_facade::{Wrapped, Point, Opaque, Status, make, status};

pub fn main() -> Int {
    Opaque {};
    42
}
