module list_api_with_abandonment;

import collections::list::{List};
import core::option::{Option};
import eldude::fixture::{File, acquire, close, yield};

fn inspect<
    T,
    R,
    !e,
    ..C
>(
    view values: List<T>,
    callback: fn(view T) ->{| e} R captures {..C},
) ->{| e} Option<R> where ..C: Discard {
    view values.with(0, callback)
}

pub fn main() ->{suspend} Int {
    let values: List<File> = [acquire()];
    inspect(view values, fn(view file: File) ->{suspend} Int {
        yield();
        0
    });
    for file in values {
        close(file);
    };
    42
}
