module examples::source_pipeline::multi_operations_affine;

import eldude::fixture::{acquire, close};

effect Multi {
    tail read(value: Int) -> Int;
    once step() -> Unit;
    affine stop(answer: Int) -> Unit;
}

pub fn main() -> Int {
    let outside = acquire();
    let answer = handle {
        using (body = acquire()) {
            handle {
                !Multi::step();
                !Multi::stop(7);
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
    };
    close(outside);
    answer
}
