module reject::operation_arguments::abandonment;

import eldude::fixture::{acquire, close, yield};

effect Echo {
    tail echo(value: Int, marker: Unit) -> Int;
}

pub fn main() ->{suspend} Int {
    let file = acquire();
    let answer = handle {
        !Echo::echo(42, yield())
    } with handler Echo {
        echo(value, _) => value;
    };
    close(file);
    answer
}
