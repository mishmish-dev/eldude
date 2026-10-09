module reject::source_pipeline::repeated_resume;

effect Step {
    once step() -> Unit;
}

pub fn main() -> Unit {
    handle {
        !Step::step()
    } with handler Step {
        step() => {
            resume(());
            resume(())
        };
    }
}
