module library_map_linear_callback;

import core::option::{Option};
import eldude::fixture::{File, acquire, close};

pub fn main() -> Int {
    let file = acquire();
    let absent: Option<Int> = Option::None;
    absent.map(fn(n: Int) -> Int captures {file} {
        close(file);
        n
    });
    0
}
