module examples::tasks::runtime_inherited_closure;

effect Read {
    tail value() -> Int;
}

pub fn main() ->{suspend} Int {
    handle {
        taskgroup {
            let child = spawn {
                taskgroup {
                    let grandchild = spawn {
                        fn() => !outer::value()
                    };
                    await grandchild
                }
            };
            let read = await child;
            read()
        }
    } with outer = handler Read {
        value() => 42;
    }
}

pub fn verify() ->{suspend} Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
