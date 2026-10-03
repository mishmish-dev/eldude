module examples::reject::multiple_row_tails;

effect Log { tail write() -> Unit; }

// An effect row has at most one tail after |.
fn work<!e, !f>() ->{Log | e, f} Unit;
