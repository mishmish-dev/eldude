module examples::reject::multi_operations::unsafe_affine;

import eldude::fixture::{acquire, close};

effect Multi {
    tail read(x: Int) -> Int;
    once step() -> Unit;
    affine stop(x: Int) -> Unit;
}

pub fn main() -> Int {
    handle {
        let file = acquire(); /*error*/
        !Multi::stop(7);
        close(file);
        42
    } with handler Multi {
        read(x) => x;
        step() => resume(());
        stop(x) => x;
    }
}
