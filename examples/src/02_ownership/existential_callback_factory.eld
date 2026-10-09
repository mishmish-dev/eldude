module existential_callback_factory;

trait Relay {
    fn relay(self, f: fn() -> Int) -> fn() -> Int captures {f};
}

struct A {}

impl Relay for A {
    fn relay(self, f: fn() -> Int) -> fn() -> Int captures {f} {
        f
    }
}

pub fn main() -> Int {
    let item: any Relay = A {};
    let done = item.relay(fn() {
        42
    });
    done()
}

pub fn verify() -> Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
