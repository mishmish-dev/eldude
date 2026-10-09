module capture_trait_bounds;

trait Repeat<..C> where ..C: Dup + Discard {
    type Callback;
    fn make(view self) -> Self::Callback;
    fn repeat(view self, f: fn() -> Int captures {..C}) -> Int;
}

struct A {}

impl<..C> Repeat<..C> for A where ..C: Dup + Discard {
    type Callback = fn() -> Int captures {..C};
    fn make(view self) -> fn() -> Int captures {..C} {
        fn() {
            21
        }
    }
    fn repeat(view self, f: fn() -> Int captures {..C}) -> Int {
        f() + f()
    }
}

fn invoke<
    ..C
>(
    view item: any Repeat<..C, Callback = fn() -> Int captures {..C}> + Discard,
    f: fn() -> Int captures {..C}
) -> Int where ..C: Dup + Discard {
    view item.repeat(f)
}

pub fn main() -> Int {
    let item: any Repeat<{}, Callback = fn() -> Int> + Discard = A {};
    if invoke(view item, fn() {
        21
    }) == 42 {
        let done = view item.make();
        done() + done()
    } else {
        0
    }
}
