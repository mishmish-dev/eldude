module reject::source_pipeline::outward_pending;
import eldude::fixture::{acquire, close};
effect Step { once step() -> Unit; }
effect Stop { affine stop() -> Unit; }
pub fn main() -> Unit {
    handle {
        handle {
            let file = acquire();
            !Step::step();
            close(file)
        } with handler Step {
            step() => { !stop::stop(); resume(()) };
        }
    } with stop = handler Stop { stop() => (); }
}
