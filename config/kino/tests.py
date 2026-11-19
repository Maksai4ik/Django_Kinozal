from django.test import SimpleTestCase

from .forms import RegisterForm


class RegisterFormTests(SimpleTestCase):
    def test_registration_fields_are_russian_without_help_text(self):
        form = RegisterForm()

        self.assertEqual(form.fields["password1"].label, "Пароль")
        self.assertEqual(
            form.fields["password2"].label,
            "Подтверждение пароля",
        )
        for field_name in ("username", "password1", "password2"):
            self.assertEqual(form.fields[field_name].help_text, "")
