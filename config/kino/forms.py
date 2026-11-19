from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import Review


# Форма регистрации нового пользователя
class RegisterForm(UserCreationForm):
    # Добавляем поле электронной почты поверх стандартных полей регистрации
    email = forms.EmailField(label="Электронная почта", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].help_text = ""
        self.fields["password1"].label = "Пароль"
        self.fields["password1"].help_text = ""
        self.fields["password2"].label = "Подтверждение пароля"
        self.fields["password2"].help_text = ""

    class Meta:
        model = User
        fields = ("username", "email")
        labels = {
            "username": "Имя пользователя",
        }


# Форма редактирования профиля пользователя
class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("username", "first_name", "last_name", "email")
        labels = {
            "username": "Имя пользователя",
            "first_name": "Имя",
            "last_name": "Фамилия",
            "email": "Электронная почта",
        }


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
            "text": forms.Textarea(attrs={"rows": 3}),
        }
