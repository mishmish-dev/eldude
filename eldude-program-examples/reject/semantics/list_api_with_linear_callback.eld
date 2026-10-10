module list_api_with_linear_callback;

import collections::list::{List};
import eldude::fixture::{acquire, close};

pub fn main() -> Int {
    let values = [1];
    let resource = acquire();
    view values.with(0, fn(view item: Int) -> Int captures {resource} {
        close(resource);
        item
    });
    42
}
