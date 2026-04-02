import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


class ComplexityPasswordValidator:
    message = _(
        "Password must include at least one uppercase letter, one lowercase letter, one digit, and one symbol."
    )

    def validate(self, password, user=None):
        checks = [
            r"[A-Z]",
            r"[a-z]",
            r"[0-9]",
            r"[^A-Za-z0-9]",
        ]
        if not all(re.search(pattern, password or "") for pattern in checks):
            raise ValidationError(self.message, code="password_not_complex_enough")

    def get_help_text(self):
        return self.message
