module reject::source_pipeline::skipped_consumption;

import eldude::fixture::{acquire, close};

effect Stop {
    affine stop() -> Unit;
}

pub fn main() -> Unit {
    let file = acquire();
    handle {
        !Stop::stop();
        close(file)
    } with handler Stop {
        stop() => ();
    }
}
