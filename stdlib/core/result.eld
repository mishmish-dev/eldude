module core::result;

// Error type first, success type second.
pub enum Result<E, T> {
    pub Err(E),
    pub Ok(T),
}

impl<E, T> Result<E, T> {
    pub fn isOk(view self) -> Bool {
        match self {
            case Result::Err(_) => false;
            case Result::Ok(_) => true;
        }
    }

    pub fn map<U, !e, ..C>(
        self,
        transform: fn(T) ->{| e} U captures {..C},
    ) ->{| e} Result<E, U>
    where ..C: Discard {
        match self {
            case Result::Err(error) => Result::Err(error);
            case Result::Ok(value) => Result::Ok(transform(value));
        }
    }

    pub fn mapError<F, !e, ..C>(
        self,
        transform: fn(E) ->{| e} F captures {..C},
    ) ->{| e} Result<F, T>
    where ..C: Discard {
        match self {
            case Result::Err(error) => Result::Err(transform(error));
            case Result::Ok(value) => Result::Ok(value);
        }
    }

    pub fn andThen<U, !e, ..C>(
        self,
        transform: fn(T) ->{| e} Result<E, U> captures {..C},
    ) ->{| e} Result<E, U>
    where ..C: Discard {
        match self {
            case Result::Err(error) => Result::Err(error);
            case Result::Ok(value) => transform(value);
        }
    }
}
