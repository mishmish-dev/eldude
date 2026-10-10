module rejects::library_iteration_indirect_recursion;

enum Chain {
    End,
    Link(Chain)
}

impl Chain {
    fn length(self) -> Int {
        match self {
            case Chain::End => self.again();
            case Chain::Link(rest) => rest.length();
        }
    }
    fn again(self) -> Int {
        match self {
            case Chain::End => self.length();
            case Chain::Link(rest) => rest.again();
        }
    }
}

pub fn main() -> Int {
    42
}
