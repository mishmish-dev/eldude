module core::result;

// Value type first, error type second.
pub enum Result<T, E> {
    pub Err(E),
    pub Ok(T),
}

impl<T, E> Result<T, E> {
    pub fn isOk(view self) -> Bool {
        match self {
            case Result::Err(_) => false;
            case Result::Ok(_) => true;
        }
    }

    pub fn map<U, !e, ..C>(
        self,
        transform: fn(T) ->{| e} U captures {..C},
    ) ->{| e} Result<U, E>
    where ..C: Discard {
        match self {
            case Result::Err(error) => Result::Err(error);
            case Result::Ok(value) => Result::Ok(transform(value));
        }
    }

    pub fn mapError<F, !e, ..C>(
        self,
        transform: fn(E) ->{| e} F captures {..C},
    ) ->{| e} Result<T, F>
    where ..C: Discard {
        match self {
            case Result::Err(error) => Result::Err(transform(error));
            case Result::Ok(value) => Result::Ok(value);
        }
    }

    pub fn andThen<U, !e, ..C>(
        self,
        transform: fn(T) ->{| e} Result<U, E> captures {..C},
    ) ->{| e} Result<U, E>
    where ..C: Discard {
        match self {
            case Result::Err(error) => Result::Err(error);
            case Result::Ok(value) => transform(value);
        }
    }
}
