module examples::source_pipeline::tail_cleanup;

import eldude::fixture::{acquire, close};

effect Read {
    tail value() -> Int;
}

pub fn main() -> Int {
    handle {
        let answer = !Read::value();
        let file = acquire();
        close(file);
        answer
    } with read = handler Read {
        value() => using (temporary = acquire()) {
            40
        };
    }
}
