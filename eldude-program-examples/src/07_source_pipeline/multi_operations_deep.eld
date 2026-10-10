module examples::source_pipeline::multi_operations_deep;

import eldude::fixture::{acquire, close};

effect Multi {
    tail read(value: Int) -> Int;
    once step() -> Unit;
    affine stop(answer: Int) -> Unit;
}

effect Mark {
    tail mark() -> Unit;
}

effect Empty {}

pub fn main() -> Int {
    handle {
        let frame = acquire();
        handle {
            handle {
                !shared::step();
                !Multi::step();
                !Multi::read(42)
            } with inner = handler Multi {
                step() => resume(());
                forward read;
                forward ..;
            }
        } with shared = handler Multi {
            read(frame) => using (temporary = acquire()) {
                !Mark::mark();
                frame
            };
            step() => handle {
                ()
            } with handler Empty {
                return ignored => {
                    let answer = resume(());
                    using (after = acquire()) {
                        answer
                    }
                };
            };
            stop(answer) => {
                close(frame);
                answer
            };
            return answer => {
                close(frame);
                answer
            };
        }
    } with mark = handler Mark {
        mark() => ();
    }
}

pub fn verify() -> Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
