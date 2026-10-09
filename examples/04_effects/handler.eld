module examples::effects::basic_handler;

effect Read {
    tail value() -> Int;
}

fn answer() ->{Read} Int {
    !Read::value() + 2
}

pub fn main() -> Int {
    handle {
        answer()
    } with handler Read {
        value() => 40;
        return result => result;
    }
}
