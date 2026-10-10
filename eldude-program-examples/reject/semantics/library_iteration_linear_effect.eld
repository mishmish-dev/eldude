module rejects::library_iteration_linear_effect;

import collections::linked_list::{LinkedList};

linear struct Ticket {}

effect Stop {
    affine stop() -> Unit;
}

fn abandon(tickets: LinkedList<Ticket>) ->{Stop} Unit {
    for ticket in tickets {
        let Ticket {} = ticket;
        !Stop::stop();
    };
}

pub fn main() -> Int {
    42
}
