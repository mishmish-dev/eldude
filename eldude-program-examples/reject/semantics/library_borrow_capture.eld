module rejects::library_borrow_capture;

linear struct Ticket {}

enum Packet {
    Held(Ticket)
}

fn escape(view packet: Packet) -> fn() -> Bool {
    fn() {
        match packet {
            case Packet::Held(_) => true;
        }
    }
}

pub fn main() -> Int {
    42
}
