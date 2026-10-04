module reject::source_pipeline::nested_return_outward;
import eldude::fixture::{acquire, close};
effect Step { once step() -> Unit; }
effect Read { tail value() -> Int; }
effect Stop { affine stop() -> Unit; }

pub fn main() -> Unit {
    handle {
        let outside = acquire();
        handle { !Step::step() } with handler Step {
            step() => handle { 1 } with handler Read {
                value() => 7;
                return answer => {
                    resume(());
                    !Stop::stop();
                };
            };
        };
        close(outside);
    } with handler Stop { stop() => (); }
}
