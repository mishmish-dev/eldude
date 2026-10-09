module examples::values::member_visibility_facade;

pub import examples::values::member_visibility_library::{
    Secret as Wrapped,
    Point,
    Opaque,
    Status,
    make,
    status
};

pub fn main() -> Int {
    let s = make();
    view s.value()
}

pub fn verify() -> Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
