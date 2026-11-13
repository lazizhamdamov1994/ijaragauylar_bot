class ServiceError(Exception):
    """Biznes xatosi. `code` — texts faylidagi kalit, foydalanuvchiga shu matn ko'rsatiladi."""

    def __init__(self, code: str, **params):
        super().__init__(code)
        self.code = code
        self.params = params


class ValidationError(ServiceError):
    pass


class NotFoundError(ServiceError):
    pass


class ConflictError(ServiceError):
    pass
