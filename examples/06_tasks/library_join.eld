module examples::tasks::library_join;

import task::{join2};

pub fn main() ->{suspend} Int {
    let (left, right) = join2(fn() => 19, fn() => 23);
    left + right
}
