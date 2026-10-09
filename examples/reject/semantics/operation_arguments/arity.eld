module reject::operation_arguments::wrong_arity;

effect Echo {
    tail echo(value: Int) -> Int;
}

pub fn main() -> Int {
    handle {
        !Echo::echo()
    } with handler Echo {
        echo(value) => value;
    }
}
