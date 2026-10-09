module examples::source_pipeline::nested_return;

import eldude::fixture::{acquire, close};

effect Read {
    tail value() -> Int;
}

effect Step {
    once step() -> Unit;
}

pub fn main() -> Int {
    let frame = acquire();
    handle {
        !Step::step();
        !Step::step();
        42
    } with step = handler Step {
        step() => handle {
            using (temporary = acquire()) {
                !Read::value()
            }
        } with read = handler Read {
            value() => 7;
            return value => {
                let answer = resume(());
                using (post = acquire()) {
                    answer
                }
            };
        };
        return answer => {
            close(frame);
            answer
        };
    }
}
