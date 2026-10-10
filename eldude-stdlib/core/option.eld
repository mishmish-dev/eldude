module core::option;

pub enum Option<T> {
    pub None,
    pub Some(T),
}

impl<T> Option<T> {
    pub fn isSome(view self) -> Bool {
        match self {
            case Option::None => false;
            case Option::Some(_) => true;
        }
    }

    pub fn map<U, !e, ..C>(
        self,
        transform: fn(T) ->{| e} U captures {..C},
    ) ->{| e} Option<U>
    where ..C: Discard {
        match self {
            case Option::None => Option::None;
            case Option::Some(value) => Option::Some(transform(value));
        }
    }

    pub fn andThen<U, !e, ..C>(
        self,
        transform: fn(T) ->{| e} Option<U> captures {..C},
    ) ->{| e} Option<U>
    where ..C: Discard {
        match self {
            case Option::None => Option::None;
            case Option::Some(value) => transform(value);
        }
    }
}
