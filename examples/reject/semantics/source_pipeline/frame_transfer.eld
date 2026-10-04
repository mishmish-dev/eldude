module reject::source_pipeline::frame_transfer;
import eldude::fixture::{acquire, close};
effect Step { once step() -> Unit; }
pub fn main() -> Unit {
    let file = acquire();
    handle { !Step::step() } with handler Step {
        step() => {
            resume(());
            close(file)
        };
        return answer => close(file);
    }
}
