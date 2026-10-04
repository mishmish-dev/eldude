module examples::source_pipeline::operation_arguments;
import eldude::fixture::{acquire, close};
effect Echo { tail echo(value: Int, marker: Unit) -> Int; }
effect Step { once step(value: Int) -> Int; }

fn request(value: Int) ->{Echo} Int { !Echo::echo(value, ()) }

pub fn main() -> Int {
    let frame = acquire();
    handle {
        handle {
            !Step::step(7);
            !Step::step(42)
        } with step = handler Step {
            step(input) => handle { request(input) } with inner = handler Echo {
                forward echo;
                return value => {
                    let answer = resume(value);
                    using (post = acquire()) { answer }
                };
            };
            return answer => { close(frame); answer };
        }
    } with outer = handler Echo {
        echo(value, _) => using (temporary = acquire()) { value };
    }
}
