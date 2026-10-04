module reject::source_pipeline::skipped_outer_resume;
effect Step { once step() -> Unit; }
effect Stop { affine stop() -> Unit; }
pub fn main() -> Unit {
    handle { !Step::step() } with handler Step {
        step() => {
            handle {
                !Stop::stop();
                resume(())
            } with handler Stop { stop() => (); }
        };
    }
}
