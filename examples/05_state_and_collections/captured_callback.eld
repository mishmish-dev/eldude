module examples::state::captured_callback;
import state::ref::{Ref};

fn relay<@r>(f: fn() ->{state<@r>} Int captures {@r})
    -> fn() ->{state<@r>} Int captures {@r} {
    f
}

pub fn main() -> Int {
    region local {
        let cell: Ref<Int, @local> = Ref::new(42);
        let read: fn() ->{state<@local>} Int captures {cell} =
            fn() ->{state<@local>} Int captures {@local} { cell.get() };
        let callback = relay(read);
        callback()
    }
}
