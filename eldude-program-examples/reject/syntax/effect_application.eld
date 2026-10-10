module examples::reject::effect_application;

effect Read<T> { tail value() -> T; }

fn read() ->{Read<Int>} Int { !Read<Int>::value() }
