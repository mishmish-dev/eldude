module examples::source_pipeline::once_deep;

import eldude::fixture::{acquire, close};

effect Step {
    once step() -> Unit;
}

pub fn main() -> Int {
    let file = acquire();
    handle {
        !Step::step();
        !Step::step();
        42
    } with step = handler Step {
        step() => {
            resume(());
            99
        };
        return answer => {
            close(file);
            answer
        };
    }
}
