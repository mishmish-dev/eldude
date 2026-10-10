module examples::values::member_visibility_library;

pub struct Secret {
    x: Int
}

pub struct Point {
    pub x: Int
}

pub struct Opaque;

pub enum Status {
    pub Ready(Int),
    Hidden(Int),
    pub Named {
        pub value: Int
    },
    pub Concealed {
        value: Int
    }
}

impl Secret {
    fn hidden(view self) -> Int {
        self.x
    }
    pub fn value(view self) -> Int {
        view self.hidden()
    }
}

pub fn make() -> Secret {
    Secret { x: 42 }
}

pub fn status() -> Status {
    Status::Hidden(42)
}

pub fn main() -> Int {
    let s = make();
    let Secret { x } = s;
    let concealed = Status::Concealed { value: x };
    let n = match concealed {
        case Status::Concealed { value } => value;
        case _ => 0;
    };
    let visible = Point { x: n };
    match status() {
        case Status::Hidden(n) => n;
        case _ => visible.x;
    }
}

pub fn verify() -> Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
