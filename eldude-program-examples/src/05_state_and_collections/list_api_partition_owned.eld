module list_api_partition_owned;

import collections::list::{List};
import eldude::fixture::{File, acquire, close};

pub fn main() -> Int {
    let values: List<File> = [acquire(), acquire(), acquire()];
    let (yes, no) = values.partition(fn(view file: File) -> Bool {
        true
    });
    let size = view yes.length() + view no.length();
    for file in yes {
        close(file);
    };
    for file in no {
        close(file);
    };
    if size == 3nat {
        42
    } else {
        0
    }
}

pub fn verify() -> Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
