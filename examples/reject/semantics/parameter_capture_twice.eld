module parameter_capture_twice;

import eldude::fixture::{File, acquire, close};

fn make(file: File) -> fn() -> Unit captures {file} {
    fn() {
        close(file);
    }
}

pub fn main() -> Int {
    let finish = make(acquire());
    finish();
    finish();
    42
}
