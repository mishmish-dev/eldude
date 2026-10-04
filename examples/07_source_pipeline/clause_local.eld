module examples::source_pipeline::clause_local;
import eldude::fixture::{acquire, close};
effect Step { once step() -> Unit; }

pub fn main() -> Unit {
    handle { !Step::step() } with step = handler Step {
        step() => {
            let local = acquire();
            resume(());
            close(local)
        };
    }
}
