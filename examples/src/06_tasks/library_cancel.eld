module library_cancel;

import task::{join2, yield};
import eldude::fixture::{File, acquire};

pub fn main() ->{suspend} Int {
    taskgroup {
        let left = acquire();
        let right = acquire();
        let child = spawn join2(
            fn() ->{suspend} Int captures {left} {
                using (held = left) {
                    yield();
                    20
                }
            },
            fn() ->{suspend} Int captures {right} {
                using (held = right) {
                    yield();
                    22
                }
            },
        );
        yield();
        child.cancel();
        42
    }
}

pub fn verify() ->{suspend} Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
