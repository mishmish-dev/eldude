module reject::source_pipeline::nested_return_residual;
import eldude::fixture::{acquire, close};
effect Step { once step() -> Unit; }
effect Read { tail value() -> Int; }
effect Stop { affine stop() -> Unit; }

pub fn main() -> Unit {
    handle {
        handle { !Step::step(); !Step::step(); } with handler Step {
            step() => handle { 1 } with handler Read {
                value() => 7;
                return answer => {
                    let local = acquire();
                    // Re-entry may reach Stop before this local closes.
                    resume(());
                    close(local);
                    !Stop::stop();
                };
            };
        }
    } with handler Stop { stop() => (); }
}
