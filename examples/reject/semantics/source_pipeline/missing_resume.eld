module reject::source_pipeline::missing_resume;
effect Step { once step() -> Unit; }
pub fn main() -> Unit {
    handle { !Step::step() } with handler Step {
        step() => ();
    }
}
