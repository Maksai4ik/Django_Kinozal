import re
from pathlib import Path

from django import forms
from django.contrib.auth.forms import PasswordChangeForm, UserCreationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile

from .models import Movie, Review, UserProfile


MAX_POSTER_SIZE = 2 * 1024 * 1024


class PosterImageField(forms.ImageField):
    allowed_extensions = {
        "JPEG": {".jpg", ".jpeg"},
        "PNG": {".png"},
    }

    def to_python(self, data):
        if isinstance(data, UploadedFile) and data.size > MAX_POSTER_SIZE:
            raise ValidationError("Размер постера не должен превышать 2 МБ.")

        image = super().to_python(data)
        if not isinstance(data, UploadedFile) or image is None:
            return image

        image_format = getattr(image.image, "format", None)
        extension = Path(image.name).suffix.lower()
        if (
            image_format not in self.allowed_extensions
            or extension not in self.allowed_extensions.get(image_format, set())
        ):
            raise ValidationError("Постер должен быть в формате JPEG или PNG.")
        return image


class MovieAdminForm(forms.ModelForm):
    poster = PosterImageField(
        label="Постер",
        required=False,
        help_text="Формат JPEG или PNG, размер — до 2 МБ.",
    )

    class Meta:
        model = Movie
        fields = "__all__"


class SalesReportPeriodForm(forms.Form):
    start_date = forms.DateField(
        label="С даты",
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "input"}),
    )
    end_date = forms.DateField(
        label="По дату",
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "input"}),
    )

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        if start_date and end_date and start_date > end_date:
            self.add_error(
                "end_date",
                "Дата окончания не может быть раньше даты начала.",
            )
        return cleaned_data


# Форма регистрации нового пользователя
class RegisterForm(UserCreationForm):
    # Добавляем поле электронной почты поверх стандартных полей регистрации
    email = forms.EmailField(
        label="Электронная почта",
        max_length=254,
        required=True,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].help_text = ""
        self.fields["password1"].label = "Пароль"
        self.fields["password1"].help_text = ""
        self.fields["password1"].widget.attrs["minlength"] = 8
        self.fields["password2"].label = "Подтверждение пароля"
        self.fields["password2"].help_text = ""
        self.fields["password2"].widget.attrs["minlength"] = 8

    class Meta:
        model = User
        fields = ("username", "email")
        labels = {
            "username": "Имя пользователя",
        }


# Форма редактирования профиля пользователя
class ProfileForm(forms.ModelForm):
    email = forms.EmailField(
        label="Электронная почта",
        max_length=254,
        required=True,
    )
    phone = forms.CharField(
        label="Телефон",
        required=False,
        max_length=32,
        widget=forms.TextInput(attrs={"type": "tel", "autocomplete": "tel"}),
    )

    class Meta:
        model = User
        fields = ("username", "first_name", "last_name", "email")
        labels = {
            "username": "Имя пользователя",
            "first_name": "Имя",
            "last_name": "Фамилия",
            "email": "Электронная почта",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["phone"].initial = (
                UserProfile.objects.filter(user=self.instance)
                .values_list("phone", flat=True)
                .first()
                or ""
            )

    def clean_phone(self):
        phone = self.cleaned_data["phone"].strip()
        if not phone:
            return phone

        if not re.fullmatch(r"\+?[\d\s().-]+", phone):
            raise ValidationError(
                "Введите телефон, используя цифры, пробелы, скобки, дефис и знак +."
            )

        digits = re.sub(r"\D", "", phone)
        if not 10 <= len(digits) <= 15:
            raise ValidationError("Телефон должен содержать от 10 до 15 цифр.")
        return phone


class AccountPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        labels = {
            "old_password": "Текущий пароль",
            "new_password1": "Новый пароль",
            "new_password2": "Подтверждение нового пароля",
        }
        for field_name, label in labels.items():
            self.fields[field_name].label = label
            self.fields[field_name].help_text = ""


# Форма добавления отзыва к фильму
class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ("rating", "text")
        labels = {
            "rating": "Оценка",
            "text": "Текст отзыва",
        }
        widgets = {
            "text": forms.Textarea(attrs={"rows": 3, "maxlength": 1000}),
        }
