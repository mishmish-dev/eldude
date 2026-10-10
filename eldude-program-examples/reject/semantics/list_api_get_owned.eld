module list_api_get_owned;

import collections::list::{List};
import eldude::fixture::{File, acquire};

pub fn main() -> Int {
    let values: List<File> = [acquire()];
    view values.get(0);
    42
}
