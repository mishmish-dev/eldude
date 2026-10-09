module library_combinators;

import core::option::{Option};
import core::result::{Result};
import state::ref::{Ref};

pub fn main() -> Int {
    region local {
        let calls: Ref<Int, @local> = Ref::new(0);
        let present = Option::Some(20);
        let absent: Option<Int> = Option::None;
        let failed: Result<Int, Int> = Result::Err(21);
        let succeeded: Result<Int, Int> = Result::Ok(20);
        let flags = (
            view present.isSome(),
            view absent.isSome(),
            view succeeded.isOk(),
            view failed.isOk()
        );
        let mapped = present.map(
            fn(n: Int) ->{state<@local>} Int captures {calls} {
                calls.set(calls.get() + 1);
                n + 1
            }
        ).andThen(fn(n: Int) -> Option<Int> {
            Option::Some(n + 1)
        });
        let skipped = absent.map(
            fn(n: Int) ->{state<@local>} Int captures {calls} {
                calls.set(100);
                n
            }
        );
        let recovered = failed.mapError(fn(n: Int) -> Int {
            n + 1
        });
        let result = succeeded.map(
            fn(n: Int) -> Int {
                n + 1
            }
        ).andThen(fn(n: Int) -> Result<Int, Int> {
            Result::Ok(n - 1)
        });
        match (flags, mapped, skipped, recovered, result) {
            case (
                (true, false, true, false),
                Option::Some(a),
                Option::None,
                Result::Err(22),
                Result::Ok(c)
            ) => if calls.get() == 1 {
                a + c
            } else {
                0
            };
            case _ => 0;
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
