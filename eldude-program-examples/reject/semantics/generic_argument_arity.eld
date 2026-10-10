module generic_argument_arity;

fn call<@r>(f: fn() -> Int captures {@r}) -> Int {
    f()
}

pub fn main() -> Int {
    region local {
        call::<@local, @local>(fn() {
            42
        })
    }
}
