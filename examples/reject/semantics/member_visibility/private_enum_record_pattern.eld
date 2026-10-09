module reject::private_enum_record_pattern;

import examples::values::member_visibility_facade::{Status, status};

pub fn main() -> Int {
    match status() {
        case Status::Concealed { value } => value;
        case _ => 0;
    }
}
