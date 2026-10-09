module rejects::library_iteration_recursive_method;

enum Chain {
    End,
    Link(Chain)
}

impl Chain {
    fn length(self) -> Int {
        self.length()
    }
}

pub fn main() -> Int {
    42
}
