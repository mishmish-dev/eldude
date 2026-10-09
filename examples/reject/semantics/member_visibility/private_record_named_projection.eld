module reject::private_record_named_projection;

import examples::values::member_visibility_facade::{Wrapped, Point, Opaque, Status, make, status};

pub fn main() -> Int {
    let s = make();
    s.x
}
