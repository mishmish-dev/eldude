module rejects::library_iteration_linear_return;

import collections::linked_list::{LinkedList};

linear struct Ticket {}

fn abandon(tickets: LinkedList<Ticket>) -> Int {
    for ticket in tickets {
        let Ticket {} = ticket;
        return 42;
    };
    0
}

pub fn main() -> Int {
    42
}
