module reject::source_pipeline::nested_return_affine_skip;

effect Step {
    once step() -> Unit;
}

effect Stop {
    affine stop() -> Unit;
}

pub fn main() -> Unit {
    handle {
        !Step::step()
    } with handler Step {
        step() => handle {
            !Stop::stop()
        } with handler Stop {
            stop() => ();
            // Zero resumption would skip this required outer resume.
            return answer => resume(());
        };
    }
}
