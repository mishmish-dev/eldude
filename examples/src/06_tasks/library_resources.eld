module library_resources;

import task::{join2, yield};
import eldude::fixture::{File, acquire, close};

fn work(file: File, number: Int) ->{suspend} Int {
    using (held = file) {
        yield();
        number
    }
}

pub fn main() ->{suspend} Int {
    let left = acquire();
    let right = acquire();
    let (a, b) = join2(
        fn() ->{suspend} Int captures {left} {
            work(left, 20)
        },
        fn() ->{suspend} Int captures {right} {
            work(right, 22)
        },
    );
    a + b
}

pub fn verify() ->{suspend} Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
