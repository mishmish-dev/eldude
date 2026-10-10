module reject::source_pipeline::unsafe_affine;

import eldude::fixture::{acquire, close};

effect Stop {
    affine stop() -> Unit;
}

pub fn main() -> Unit {
    handle {
        let file = acquire();
        !Stop::stop();
        close(file)
    } with handler Stop {
        stop() => ();
    }
}
