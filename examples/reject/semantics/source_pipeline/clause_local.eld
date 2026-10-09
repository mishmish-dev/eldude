module reject::source_pipeline::clause_local;

import eldude::fixture::{acquire};

effect Step {
    once step() -> Unit;
}

pub fn main() -> Unit {
    handle {
        !Step::step()
    } with handler Step {
        step() => {
            let local = acquire();
            resume(())
        };
    }
}
