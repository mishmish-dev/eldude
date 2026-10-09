module rejects::library_iteration_linear_length;

import collections::linked_list::{LinkedList};

linear struct Ticket {}

fn discard(tickets: LinkedList<Ticket>) -> Nat {
    tickets.length()
}

pub fn main() -> Int {
    42
}
