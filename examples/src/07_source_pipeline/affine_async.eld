module examples::source_pipeline::affine_async;

import eldude::fixture::{acquireAsync, yield};

effect Stop {
    affine stop() -> Unit;
}

pub fn main() ->{suspend} Unit {
    handle {
        using (file = acquireAsync()) {
            !Stop::stop();
            yield();
        }
    } with stop = handler Stop {
        stop() => ();
    }
}

pub fn verify() ->{suspend} Int {
    if main() == () {
        0
    } else {
        1
    }
}
