module nonabandoning;

import eldude::fixture::{acquire, close};

effect Read {
    tail read() -> Int;
}

fn use<!e>(f: fn() ->{| e} Int) ->{| e} Int where e: NonAbandoning {
    let file = acquire();
    let result = f();
    close(file);
    result
}

fn relay<!e>(f: fn() ->{| e} Int) ->{| e} Int where e: NonAbandoning {
    use(f)
}

pub fn main() -> Int {
    handle {
        relay(fn() {
            !Read::read()
        })
    } with handler Read {
        read() => 42;
        return x => x;
    }
}

pub fn verify() -> Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
