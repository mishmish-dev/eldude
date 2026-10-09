module list_api_replace_empty_owned;

import collections::list::{List};
import eldude::fixture::{acquire};

pub fn main() -> Int {
    [].replace(0, acquire());
    42
}
