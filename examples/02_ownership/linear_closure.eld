module examples::ownership::linear_closure;

linear struct Ticket { number: Int }

fn redeem(ticket: Ticket) -> Int {
    let Ticket { number } = ticket;
    number
}

pub fn main() -> Int {
    let ticket = Ticket { number: 42 };
    let finish = fn() => redeem(ticket);
    finish()
}
