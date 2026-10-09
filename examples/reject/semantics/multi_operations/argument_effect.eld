module examples::reject::multi_operations::argument_effect;

import eldude::fixture::{acquire, close};

effect Multi {
    tail read(x: Int) -> Int;
    once step() -> Unit;
    affine stop(x: Int) -> Unit;
}

effect Other {
    tail get() -> Int;
}

fn request() ->{Multi} Int {
    !Multi::read( /*error*/
        !Other::get()
    )
}

pub fn main() -> Int {
    42
}
