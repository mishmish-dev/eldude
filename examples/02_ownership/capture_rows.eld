module capture_rows;

import eldude::fixture::{File, acquire, close};

fn defer<..C>(f: fn() -> Unit captures {..C}) -> fn() -> Unit captures {..C} {
    f
}

fn repeat<..C>(f: fn() -> Int captures {..C}) -> Int where ..C: Dup + Discard {
    f() + f()
}

pub fn main() -> Int {
    let file = acquire();
    let done = defer(fn() {
        close(file);
    });
    done();
    repeat(fn() {
        21
    })
}
