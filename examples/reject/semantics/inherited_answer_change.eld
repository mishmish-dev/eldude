module examples::reject::inherited_answer_change;

effect Read { tail value() -> Int; }

fn main() ->{suspend} Int {
    handle {
        taskgroup {
            let child = spawn (!Read::value() == 21);
            await child
        }
    } with handler Read {
        value() => 21;
        return flag => if flag { 42 } else { 0 };
    }
}
