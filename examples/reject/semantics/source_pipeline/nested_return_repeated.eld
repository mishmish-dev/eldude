module reject::source_pipeline::nested_return_repeated;
effect Step { once step() -> Unit; }
effect Read { tail value() -> Int; }

pub fn main() -> Unit {
    handle { !Step::step() } with handler Step {
        step() => {
            handle { 1 } with handler Read {
                value() => 7;
                return answer => resume(());
            };
            resume(());
        };
    }
}
