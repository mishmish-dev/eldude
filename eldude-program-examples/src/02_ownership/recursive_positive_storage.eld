module examples::ownership::recursive_positive_storage;

struct Box<T> {
    item: T
}

enum Chain {
    End,
    Link(Box<(Int, Chain)>)
}

enum Left {
    End,
    Link(Right)
}

enum Right {
    Link(Int, Left)
}

struct Callback {
    run: fn(Int) -> Int
}

pub fn main() -> Int {
    let chain = Chain::Link(Box { item: (19, Chain::End) });
    let n = match chain {
        case Chain::End => 0;
        case Chain::Link(box) => {
            let Box { item: (value, _) } = box;
            value
        };
    };
    let left = Left::Link(Right::Link(23, Left::End));
    let m = match left {
        case Left::End => 0;
        case Left::Link(Right::Link(value, _)) => value;
    };
    let callback = Callback { run: fn(x: Int) => x };
    callback.run(n + m)
}

pub fn verify() -> Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
