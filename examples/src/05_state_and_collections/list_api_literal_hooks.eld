module list_api_literal_hooks;

pub fn main() -> Int {
    let values = [1];
    values.remove(0);
    values.replace(0, 2);
    values.next();
    42
}

pub fn verify() -> Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
