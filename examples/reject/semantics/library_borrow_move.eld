module rejects::library_borrow_move;

linear struct Ticket {}

enum Packet {
    Held(Ticket)
}

fn steal(view packet: Packet) -> Ticket {
    match packet {
        case Packet::Held(ticket) => ticket;
    }
}

pub fn main() -> Int {
    42
}
