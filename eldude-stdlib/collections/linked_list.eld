module collections::linked_list;

import core::iter::{Iterator, Next};

pub enum LinkedList<T> {
    pub Nil,
    pub Cons { pub head: T, pub tail: LinkedList<T> },
}

impl<T> LinkedList<T> {
    pub fn prepend(self, value: T) -> LinkedList<T> {
        LinkedList::Cons { head: value, tail: self }
    }

    pub fn length(self) -> Nat
    where T: Discard {
        match self {
            case LinkedList::Nil => 0nat;
            case LinkedList::Cons { head: _, tail } => 1nat + tail.length();
        }
    }
}

impl<T> Iterator for LinkedList<T> {
    type Item = T;

    fn next(self) -> Next<LinkedList<T>, T> {
        match self {
            case LinkedList::Nil => Next::Done;
            case LinkedList::Cons { head, tail } => Next::Item(head, tail);
        }
    }
}
