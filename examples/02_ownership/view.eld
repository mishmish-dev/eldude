module examples::ownership::scoped_view;

linear struct Ticket {
    number: Int
}

fn number(view ticket: Ticket) -> Int {
    ticket.number
}

fn redeem(ticket: Ticket) -> Int {
    let Ticket { number } = ticket;
    number
}

pub fn main() -> Int {
    let ticket = Ticket { number: 21 };
    let observed = number(view ticket);
    observed + redeem(ticket)
}
