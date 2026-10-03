module examples::values::enums;

enum Choice { Left(Int), Right(Int) }

fn value(choice: Choice) -> Int {
    match choice {
        case Choice::Left(x) => x;
        case Choice::Right(x) => x + 1;
    }
}

pub fn main() -> Int {
    value(Choice::Right(41))
}
