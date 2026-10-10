module task;

// Runtime observation handle; spawn supplies its hidden group provenance.
pub affine struct Task<T> where T: Discard;

impl<T> Task<T> where T: Discard {
    pub fn cancel(self) -> Unit;
}

pub fn yield() ->{suspend} Unit;

// Both children adapt to the group's single ambient row.
pub fn join2<A, B, !e, ..Ca, ..Cb>(
    left: fn() ->{suspend | e} A captures {..Ca},
    right: fn() ->{suspend | e} B captures {..Cb},
) ->{suspend | e} (A, B)
where A: Discard, B: Discard {
    taskgroup {
        let first = spawn left();
        let second = spawn right();
        (await first, await second)
    }
}
