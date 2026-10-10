module examples::collections::library_iteration_linked_list;

import collections::linked_list::{LinkedList};
import core::iter::{Next};
import state::ref::{Ref};

linear struct Ticket {
    number: Int
}

pub fn main() -> Int {
    let empty: LinkedList<Int> = LinkedList::Nil;
    let counts = empty.prepend(1).prepend(2).prepend(3);
    let correctLength = counts.length() == 3nat;
    let first = match counts.next() {
        case Next::Done => 0;
        case Next::Item(head, _) => head;
    };
    let noTickets: LinkedList<Ticket> = LinkedList::Nil;
    let tickets = noTickets.prepend(Ticket { number: 19 }).prepend(Ticket { number: 20 });
    region r {
        let total: Ref<Int, @r> = Ref::new(0);
        for ticket in tickets {
            let Ticket { number } = ticket;
            total.set(total.get() + number);
        };
        if correctLength {
            total.get() + first
        } else {
            0
        }
    }
}

pub fn verify() -> Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
