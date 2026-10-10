module examples::effects::runtime_abandon_cleanup;

import eldude::fixture::{acquire};

effect Stop {
    affine stop() -> Unit;
}

fn descend(n: Int) ->{Stop, diverge} Unit {
    using (file = acquire()) {
        if n == 0 {
            !Stop::stop();
        } else {
            descend(n - 1);
        }
    }
}

pub fn main() ->{diverge} Int {
    handle {
        descend(2048);
        0
    } with handler Stop {
        stop() => 42;
    }
}

pub fn verify() ->{diverge} Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
