class PrivacyError(Exception):
    """Errore di dominio con codice stabile per l'API."""

    status = 400

    def __init__(self, code, message="", status=None):
        super().__init__(message or code)
        self.code = code
        self.message = message or code
        if status is not None:
            self.status = status


class Conflict(PrivacyError):
    status = 409


class NotAllowed(PrivacyError):
    status = 403


class Gone(PrivacyError):
    status = 410
