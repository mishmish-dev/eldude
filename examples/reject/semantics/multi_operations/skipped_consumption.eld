module examples::reject::multi_operations::skipped_consumption;

import eldude::fixture::{acquire, close};

effect Multi {
    tail read(x: Int) -> Int;
    once step() -> Unit;
    affine stop(x: Int) -> Unit;
}

pub fn main() -> Int {
    let outside = acquire();
    handle { /*error*/
        !Multi::stop(7);
        close(outside);
        42
    } with handler Multi {
        read(x) => x;
        step() => resume(());
        stop(x) => x;
    }
}
