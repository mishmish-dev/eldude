module reject::private_opaque_pattern;

import examples::values::member_visibility_facade::{Wrapped, Point, Opaque, Status, make, status};

pub fn main() -> Int {
    fn(x: Opaque) => {
        let Opaque {} = x;
        42
    };
    42
}
