module list_storage_snapshots;

import collections::list::{List};
import core::iter::{Iterator, Next};
import core::result::{Result};

struct Snapshot {
    values: List<Int>
}

fn require(check: Bool) -> Unit {
    if check {
        ()
    } else {
        1 / 0;
        ()
    }
}

pub fn main() -> Int {
    let base = [10, 20];
    let saved = Snapshot { values: base };
    let extended = base.push(30);
    let branch = base.push(40);
    let original = saved.values;
    require(view original.length() == 2nat);
    require((view original.get(2) ?? -1) == -1);
    require((view extended.get(2) ?? -1) == 30);
    require((view branch.get(2) ?? -1) == 40);
    match extended.next() {
        case Next::Done => 0;
        case Next::Item(first, tail) => {
            require(first == 10);
            let grown = tail.push(50);
            let alternate = tail.push(60);
            require(view tail.length() == 2nat);
            require((view tail.get(2) ?? -1) == -1);
            require((view grown.get(2) ?? -1) == 50);
            require((view alternate.get(2) ?? -1) == 60);
            require(view extended.length() == 3nat);
            let filtered = grown.filter(fn(view item: Int) -> Bool {
                item > 20
            });
            let (low, high) = grown.partition(fn(view item: Int) -> Bool {
                item < 30
            });
            require(view filtered.length() == 2nat);
            require((view filtered.get(1) ?? -1) == 50);
            require(view low.length() == 1nat);
            require(view high.length() == 2nat);
            match grown.remove(0) {
                case Result::Err((error, untouched)) => 0;
                case Result::Ok((old, rest)) => {
                    require(old == 20);
                    require(view rest.length() == 2nat);
                    require((view rest.get(0) ?? -1) == 30);
                    match tail.replace(1, 99) {
                        case Result::Err((error, untouched, incoming)) => 0;
                        case Result::Ok((previous, updated)) => {
                            require(previous == 30);
                            require((view updated.get(1) ?? -1) == 99);
                            require((view tail.get(1) ?? -1) == 30);
                            42
                        };
                    }
                };
            }
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
