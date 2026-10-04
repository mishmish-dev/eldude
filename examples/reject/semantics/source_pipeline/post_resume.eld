module reject::source_pipeline::post_resume;
import eldude::fixture::{acquire, close};
effect Step { once step() -> Unit; }
effect Stop { affine stop() -> Unit; }
pub fn main() -> Unit {
    handle {
        let file = acquire();
        handle { !Step::step() } with handler Step {
            step() => { resume(()); !stop::stop() };
        };
        close(file)
    } with stop = handler Stop { stop() => (); }
}
