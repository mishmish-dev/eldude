module reject::private_inherent_method;

import examples::values::member_visibility_facade::{Wrapped, Point, Opaque, Status, make, status};

pub fn main() -> Int {
    let s = make();
    view s.hidden()
}
