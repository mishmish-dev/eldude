module examples::source_pipeline::affine_scope;

import eldude::fixture::{acquire, close};

effect Stop {
    affine stop() -> Unit;
}

pub fn main() -> Int {
    let outside = acquire();
    let frame = acquire();
    handle {
        using (inside = acquire()) {
            !Stop::stop()
        }
    } with stop = handler Stop {
        stop() => close(frame);
        return answer => close(frame);
    };
    close(outside);
    7
}

pub fn verify() -> Int {
    if main() == 7 {
        0
    } else {
        1
    }
}
