module list_storage_owned;

import collections::dyn_array::{DynArray};
import collections::list::{List};
import core::iter::{Iterator, Next};
import eldude::fixture::{File, acquire, close};

pub fn main() -> Int {
    region local {
        let buffer: DynArray<File, @local> = DynArray::new();
        mut buffer.push(acquire());
        mut buffer.push(acquire());
        let values = buffer.freeze().push(acquire());
        match values.next() {
            case Next::Done => 0;
            case Next::Item(first, tail) => {
                close(first);
                let rest = tail.push(acquire());
                for file in rest {
                    close(file);
                };
                42
            };
        }
    }
}

pub fn verify() -> Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
