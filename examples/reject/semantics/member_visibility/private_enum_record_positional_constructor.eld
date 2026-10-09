module reject::private_enum_record_positional_constructor;

import examples::values::member_visibility_facade::{Status, status};

pub fn main() -> Int {
    Status::Concealed(42);
    42
}
