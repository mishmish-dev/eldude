module examples::source_pipeline::combined;
import eldude::fixture::{acquire, close};
effect Read { tail value() -> Int; }
effect Step { once step() -> Unit; }

fn fetch() ->{Read} Int { !Read::value() }

pub fn main() -> Int {
    let frame = acquire();
    handle {
        using (body = acquire()) {
            handle {
                !Step::step();
                !Step::step();
                handle { fetch() } with inner = handler Read {
                    forward value;
                }
            } with step = handler Step {
                step() => {
                    let answer = resume(());
                    using (post = acquire()) { answer }
                };
                return answer => { close(frame); answer };
            }
        }
    } with outer = handler Read {
        value() => using (temporary = acquire()) { 42 };
    }
}
