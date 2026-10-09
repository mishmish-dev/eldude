module reject::operation_arguments::wrong_clause_arity;

effect Echo {
    tail echo(value: Int) -> Int;
}

pub fn main() -> Int {
    handle {
        !Echo::echo(42)
    } with handler Echo {
        echo() => 42;
    }
}
