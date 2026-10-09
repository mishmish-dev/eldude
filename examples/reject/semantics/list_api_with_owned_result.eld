module list_api_with_owned_result;

import collections::list::{List};
import eldude::fixture::{File, acquire};

pub fn main() -> Int {
    let values: List<File> = [acquire()];
    view values.with(0, fn(view file: File) -> File {
        file
    });
    42
}
