module examples::reject::multi_operations::skipped_enclosing_resume;

import eldude::fixture::{acquire, close};

effect Multi {
    tail read(x: Int) -> Int;
    once step() -> Unit;
    affine stop(x: Int) -> Unit;
}

effect Flow {
    once enter() -> Unit;
    tail ping() -> Unit;
}

pub fn main() -> Int {
    handle {
        !Flow::enter();
        42
    } with handler Flow {
        ping() => ();
        enter() => handle {
            !Multi::stop(7)
        } with handler Multi {
            read(x) => x;
            step() => resume(());
            stop(x) => x;
            return x => /*error*/ resume(());
        };
    }
}
