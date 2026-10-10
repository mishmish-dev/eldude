module runtime_cancel_then_await;

pub fn main() ->{suspend} Int {
    taskgroup {
        let child = spawn 42;
        child.cancel();
        await child
    }
}
