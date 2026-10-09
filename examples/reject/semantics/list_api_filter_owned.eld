module list_api_filter_owned;

import collections::list::{List};
import eldude::fixture::{File, acquire};

pub fn main() -> Int {
    let values: List<File> = [acquire()];
    values.filter(fn(view file: File) -> Bool {
        false
    });
    42
}
