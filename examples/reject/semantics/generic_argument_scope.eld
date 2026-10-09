module generic_argument_scope;

fn call<@r>(f: fn() -> Int captures {@r}) -> Int {
    f()
}

pub fn main() -> Int {
    call::<@missing>(fn() {
        42
    })
}
