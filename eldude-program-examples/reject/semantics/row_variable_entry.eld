module examples::reject::row_variable_entry;

// A row variable belongs after |, not among the fixed effect-family entries.
fn apply<!e>(work: fn() ->{e} Unit) ->{| e} Unit {
    work()
}
