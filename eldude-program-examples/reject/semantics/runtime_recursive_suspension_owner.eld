module runtime_recursive_suspension_owner;

import task::{yield};
import eldude::fixture::{acquire, close};

fn recurse(n: Int) ->{suspend, diverge} Unit {
    let file = acquire();
    yield();
    if n != 0 {
        recurse(n - 1);
    };
    close(file);
}

pub fn main() ->{suspend, diverge} Unit {
    recurse(2048);
}
