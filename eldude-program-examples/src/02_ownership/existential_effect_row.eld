module existential_effect_row;

trait Read<!e> {
    type Callback;
    fn read(view self) ->{| e} Int;
    fn reader(view self) -> Self::Callback;
}

struct A {}

impl<!e> Read<{| e}> for A {
    type Callback = fn() ->{| e} Int;
    fn read(view self) ->{| e} Int {
        42
    }
    fn reader(view self) -> fn() ->{| e} Int {
        fn() {
            42
        }
    }
}

fn call<!e>(view item: any Read<{| e}, Callback = fn() ->{| e} Int> + Discard) ->{| e} Int {
    view item.read()
}

pub fn main() -> Int {
    let item: any Read<{}, Callback = fn() -> Int> + Discard = A {};
    let done = view item.reader();
    if call(view item) == 42 {
        done()
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
