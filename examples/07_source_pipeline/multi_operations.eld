module examples::source_pipeline::multi_operations;

import eldude::fixture::{acquire};

effect Multi {
    tail read(value: Int) -> Int;
    once step() -> Unit;
    affine stop(answer: Int) -> Unit;
}

pub fn main() -> Int {
    handle {
        using (body = acquire()) {
            handle {
                !Multi::step();
                !Multi::read(42)
            } with inner = handler Multi {
                step() => resume(());
                forward ..;
            }
        }
    } with outer = handler Multi {
        read(value) => using (temporary = acquire()) {
            value
        };
        step() => resume(());
        stop(answer) => answer;
    }
}
