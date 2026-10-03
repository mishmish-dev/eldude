module examples::reject::while_without_diverge;

// Every while admits diverge in the initial core, including this finite case.
fn run() -> Unit {
    while false {}
}
