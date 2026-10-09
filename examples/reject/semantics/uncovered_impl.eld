module examples::reject::uncovered_impl;

trait Assoc {
    type Output;
}

struct Plain {}

impl<T> Assoc for Plain {
    type Output = T;
}
