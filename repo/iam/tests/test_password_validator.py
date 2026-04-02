from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from iam.validators import ComplexityPasswordValidator


class ComplexityPasswordValidatorTests(SimpleTestCase):
    def setUp(self):
        self.validator = ComplexityPasswordValidator()

    def test_rejects_password_without_symbol(self):
        with self.assertRaises(ValidationError):
            self.validator.validate("NoSymbol123")

    def test_accepts_password_meeting_all_requirements(self):
        self.validator.validate("ValidPass123!")
