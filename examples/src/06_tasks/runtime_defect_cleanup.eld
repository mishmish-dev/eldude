module examples::tasks::runtime_defect_cleanup;

import core::cleanup::{Cleanup};
import eldude::fixture::{acquire};
import task::{yield};

linear struct Guard {}

impl Cleanup<{suspend}> for Guard {
    fn cleanup(self) ->{suspend} Unit {
        let Guard {} = self;
        yield();
        using (file = acquire()) {
            ()
        }
    }
}

fn exercise(fail: Bool) ->{suspend} Int {
    taskgroup {
        using (guard = Guard {}) {
            let child = spawn {
                if fail {
                    1 / 0
                } else {
                    42
                }
            };
            await child
        }
    }
}

pub fn main() ->{suspend} Int {
    exercise(false)
}

pub fn verify() ->{suspend} Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
