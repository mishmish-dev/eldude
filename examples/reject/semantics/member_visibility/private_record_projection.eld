module reject::private_record_projection;

import examples::values::member_visibility_facade::{Wrapped, Point, Opaque, Status, make, status};

pub fn main() -> Int {
    make().x
}
