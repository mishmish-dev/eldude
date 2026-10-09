module examples::reject::multi_operations::missing_resume;

import eldude::fixture::{acquire, close};

effect Multi {
    tail read(x: Int) -> Int;
    once step() -> Unit;
    affine stop(x: Int) -> Unit;
}

pub fn main() -> Int {
    handle {
        42
    } with handler Multi {
        read(x) => x;
        step() => /*error*/ 42;
        stop(x) => x;
    }
}
