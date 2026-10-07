module examples::ownership::existentials;

trait Read { fn read(view self) -> Int; }
struct Number { value: Int, }
struct Incremented { value: Int, }
impl Read for Number { fn read(view self) -> Int { self.value } }
impl Read for Incremented { fn read(view self) -> Int { self.value + 1 } }

fn sum(view first: any Read + Discard, view second: any Read + Discard) -> Int {
    view first.read() + view second.read()
}

pub fn main() -> Int {
    let first: any Read + Discard = Number { value: 21 };
    let second: any Read + Discard = Incremented { value: 20 };
    sum(view first, view second)
}
