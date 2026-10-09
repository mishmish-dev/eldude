module capture_row_discard;

import eldude::fixture::{File, acquire, close};

fn skip<..C>(f: fn() -> Unit captures {..C}) -> Unit where ..C: Discard {}

pub fn main() -> Int {
    let file = acquire();
    skip(fn() {
        close(file);
    });
    42
}
