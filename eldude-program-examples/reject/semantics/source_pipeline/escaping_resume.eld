module reject::source_pipeline::escaping_resume;

effect Step {
    once step() -> Unit;
}

pub fn main() -> Unit {
    handle {
        !Step::step()
    } with handler Step {
        step() => {
            let later = fn() => resume(());
            later()
        };
    }
}
