module reject::private_enum_record_constructor;

import examples::values::member_visibility_facade::{Status, status};

pub fn main() -> Int {
    Status::Concealed { value: 42 };
    42
}
