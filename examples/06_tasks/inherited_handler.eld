module examples::tasks::inherited_handler;

effect Read {
    tail value() -> Int;
}

pub fn main() ->{suspend} Int {
    handle {
        taskgroup {
            let number = spawn !Read::value();
            let flag = spawn (!Read::value() == 21);
            if await flag {
                (await number) * 2
            } else {
                await number
            }
        }
    } with handler Read {
        value() => 21;
        return result => result;
    }
}
