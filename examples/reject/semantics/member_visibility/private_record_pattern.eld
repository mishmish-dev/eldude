module reject::private_record_pattern;

import examples::values::member_visibility_facade::{Wrapped, Point, Opaque, Status, make, status};

pub fn main() -> Int {
    let Wrapped { x } = make();
    x
}
