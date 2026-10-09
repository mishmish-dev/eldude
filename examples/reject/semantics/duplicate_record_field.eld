module reject::duplicate_record_field;

import eldude::fixture::{File, acquire, close};

struct R {
    file: File
}

pub fn main() -> Unit {
    let R { file: a, file: b } = R { file: acquire() };
    close(a);
    close(b);
}
