module core::iter;

pub enum Next<I, T> {
    pub Item(T, I),
    pub Done,
}

pub trait Iterator {
    type Item;
    fn next(self) -> Next<Self, Self::Item>;
}
