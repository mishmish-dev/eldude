module examples::ownership::library_borrow_match;

import core::result::{Result};

linear struct Ticket {
    number: Int
}

enum Packet {
    Empty,
    Held(Ticket)
}

fn isHeld(view packet: Packet) -> Bool {
    match packet {
        case Packet::Empty => false;
        case Packet::Held(_) => {
            return true;
        };
    }
}

fn number(view packet: Packet) -> Int {
    match packet {
        case Packet::Empty => 0;
        case Packet::Held(Ticket { number }) => number;
    }
}

fn checked(view packet: Packet, result: Result<Int, Int>) -> Result<Int, Int> {
    let increment = result?;
    Result::Ok(number(view packet) + increment)
}

pub fn main() -> Int {
    let packet = Packet::Held(Ticket { number: 42 });
    let present = isHeld(view packet);
    let copied = number(view packet);
    let rejected = match checked(view packet, Result::Err(0)) {
        case Result::Err(error) => error;
        case Result::Ok(value) => value;
    };
    match packet {
        case Packet::Empty => 0;
        case Packet::Held(Ticket { number }) => if present {
            if copied == number {
                number + rejected
            } else {
                0
            }
        } else {
            0
        };
    }
}

pub fn verify() -> Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
