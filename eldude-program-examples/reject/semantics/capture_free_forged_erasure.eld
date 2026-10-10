module capture_free_forged_erasure;

trait Read {
    fn read(view self) -> Int;
}

struct Number {
    value: Int
}

impl Read for Number {
    fn read(view self) -> Int {
        self.value
    }
}

pub fn main() -> Int {
    let hidden: any Read + Discard = Number { value: 42 };
    let forged: any Read + CaptureFree + Discard = hidden;
    0
}
