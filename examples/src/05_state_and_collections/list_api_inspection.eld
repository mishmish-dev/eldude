module list_api_inspection;

import collections::list::{List};
import core::option::{Option};
import eldude::fixture::{File, acquire, close};
import state::ref::{Ref};

pub fn main() -> Int {
    region local {
        let values: List<File> = [acquire()];
        let calls: Ref<Int, @local> = Ref::new(0);
        let found = view values.with(
            0,
            fn(view file: File) ->{state<@local>} Int {
                calls.replace(calls.get() + 1);
                41
            }
        );
        let missing = view values.with(
            1,
            fn(view file: File) ->{state<@local>} Int {
                calls.replace(100);
                0
            }
        );
        for file in values {
            close(file);
        };
        (found ?? 0) + (missing ?? 0) + calls.get()
    }
}

pub fn verify() -> Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
