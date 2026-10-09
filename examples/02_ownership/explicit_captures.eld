module examples::ownership::explicit_captures;

import eldude::fixture::{acquire, close};

pub fn main() -> Int {
    let file = acquire();
    let finish: fn() -> Unit captures {file} = fn() {
        close(file)
    };
    finish();
    // finish owns the file, so it must be called exactly once.
    42
}
