module cleanup_abandon;

import core::cleanup::{Cleanup};
import eldude::fixture::{acquire};

linear struct Guard {}

linear struct Overflow {}

impl Cleanup<{}> for Guard {
    fn cleanup(self) -> Unit {
        let Guard {} = self;
        1 / 0;
    }
}

impl Cleanup<{}> for Overflow {
    fn cleanup(self) -> Unit {
        let Overflow {} = self;
        9223372036854775807 + 1;
    }
}

effect Stop {
    affine stop() -> Unit;
}

pub fn main() -> Int {
    handle {
        using (file = acquire()) {
            using (outer = Overflow {}) {
                using (guard = Guard {}) {
                    !Stop::stop();
                    0
                }
            }
        }
    } with handler Stop {
        stop() => 42;
    }
}
