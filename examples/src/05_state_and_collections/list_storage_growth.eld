module list_storage_growth;

import collections::list::{List};
import state::ref::{Ref};

pub fn main() ->{diverge} Int {
    region local {
        let values: Ref<List<Int>, @local> = Ref::new([]);
        let count: Ref<Int, @local> = Ref::new(0);
        while count.get() < 2048 {
            values.set(values.get().push(count.get()));
            count.set(count.get() + 1);
        };
        let snapshot = values.get();
        values.set(values.get().push(2048));
        let total: Ref<Int, @local> = Ref::new(0);
        for item in snapshot {
            total.set(total.get() + item);
        };
        total.get()
    }
}

pub fn verify() ->{diverge} Int {
    if main() == 2096128 {
        0
    } else {
        1
    }
}
