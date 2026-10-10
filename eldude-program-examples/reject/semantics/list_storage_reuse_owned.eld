module list_storage_reuse_owned;

import collections::list::{List};
import eldude::fixture::{File, acquire, close};

pub fn main() -> Unit {
    let values: List<File> = [].push(acquire());
    for file in values {
        close(file);
    };
    for file in values {
        close(file);
    };
}
