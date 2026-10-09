module list_api_partition_affine_callback;

import collections::list::{List};
import collections::dyn_array::{DynArray};

pub fn main() -> Int {
    region local {
        let values = [1];
        let captured: DynArray<Int, @local> = DynArray::new();
        values.partition(
            fn(view item: Int) -> Bool captures {captured} {
                let retained = captured;
                item == 1
            }
        );
        42
    }
}
