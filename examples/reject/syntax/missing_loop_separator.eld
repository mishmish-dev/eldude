module examples::reject::missing_loop_separator;

fn main() ->{diverge} Int {
    while false {}
    42
}
