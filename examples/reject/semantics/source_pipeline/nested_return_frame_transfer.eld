module reject::source_pipeline::nested_return_frame_transfer;
import eldude::fixture::{acquire, close};
effect Step { once step() -> Unit; }
effect Read { tail value() -> Int; }

pub fn main() -> Unit {
    let frame = acquire();
    handle { !Step::step() } with handler Step {
        step() => {
            handle { 1 } with handler Read {
                value() => 7;
                // The outer frame moves, even through this return clause.
                return answer => resume(());
            };
            close(frame);
        };
        return answer => close(frame);
    }
}
