module reject::source_pipeline::deep_residual;

import eldude::fixture::{acquire, close};

effect Step {
    once step() -> Unit;
}

effect Stop {
    affine stop() -> Unit;
}

pub fn main() -> Unit {
    handle {
        handle {
            !Step::step();
            !Step::step()
        } with handler Step {
            step() => {
                let local = acquire();
                resume(());
                close(local);
                !stop::stop()
            };
        }
    } with stop = handler Stop {
        stop() => ();
    }
}
