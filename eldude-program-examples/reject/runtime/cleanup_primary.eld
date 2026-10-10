module cleanup_primary;

import core::cleanup::{Cleanup};
import eldude::fixture::{acquire};

linear struct Guard {}

linear struct Overflow {}

impl Cleanup<{}> for Overflow {
    fn cleanup(self) -> Unit {
        let Overflow {} = self;
        9223372036854775807 + 1;
    }
}

impl Cleanup<{}> for Guard {
    fn cleanup(self) -> Unit {
        let Guard {} = self;
        using (secondary = Overflow {}) {
            9223372036854775807 + 1;
        }
    }
}

pub fn main() -> Int {
    using (file = acquire()) {
        using (outer = Guard {}) {
            using (inner = Guard {}) {
                1 / 0
            }
        }
    }
}
