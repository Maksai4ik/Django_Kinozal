from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta


class Genre(models.Model):
    name = models.CharField(max_length=50, unique=True, verbose_name="Название")

    class Meta:
        verbose_name = "Жанр"
        verbose_name_plural = "Жанры"

    def __str__(self):
        return self.name


class Movie(models.Model):
    title = models.CharField(max_length=200, verbose_name="Название")
    description = models.TextField(blank=True, verbose_name="Описание")
    duration = models.PositiveIntegerField(default=120, verbose_name="Длительность (мин)")
    year = models.PositiveIntegerField(default=2024, verbose_name="Год выпуска")
    age_limit = models.PositiveIntegerField(default=12, verbose_name="Возрастной рейтинг")
    poster = models.ImageField(upload_to='posters/', blank=True, null=True, verbose_name="Постер")
    genres = models.ManyToManyField(Genre, blank=True, verbose_name="Жанры")
    is_active = models.BooleanField(default=True, verbose_name="Показывать в афише")

    class Meta:
        verbose_name = "Фильм"
        verbose_name_plural = "Фильмы"

    def __str__(self):
        return self.title


class Hall(models.Model):
    name = models.CharField(max_length=50, verbose_name="Название зала")
    rows = models.PositiveIntegerField(default=8, verbose_name="Количество рядов")
    seats_per_row = models.PositiveIntegerField(default=12, verbose_name="Мест в ряду")

    class Meta:
        verbose_name = "Зал"
        verbose_name_plural = "Залы"

    def __str__(self):
        return self.name


class Seat(models.Model):
    hall = models.ForeignKey(Hall, on_delete=models.CASCADE, related_name="seats", verbose_name="Зал")
    row = models.PositiveIntegerField(verbose_name="Ряд")
    number = models.PositiveIntegerField(verbose_name="Место")
    is_vip = models.BooleanField(default=False, verbose_name="VIP место")

    class Meta:
        verbose_name = "Место"
        verbose_name_plural = "Места"

    def __str__(self):
        return f"Ряд {self.row}, Место {self.number}"


class Session(models.Model):
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="sessions", verbose_name="Фильм")
    hall = models.ForeignKey(Hall, on_delete=models.CASCADE, verbose_name="Зал")
    start_time = models.DateTimeField(verbose_name="Начало сеанса")
    base_price = models.DecimalField(max_digits=8, decimal_places=2, default=400, verbose_name="Цена билета")
    vip_price = models.DecimalField(max_digits=8, decimal_places=2, default=600, verbose_name="VIP цена")

    class Meta:
        verbose_name = "Сеанс"
        verbose_name_plural = "Сеансы"
        ordering = ['start_time']

    def __str__(self):
        return f"{self.movie.title} - {self.start_time.strftime('%d.%m %H:%M')}"


class Booking(models.Model):
    STATUS_CHOICES = (
        ('held', 'Удерживается'),
        ('paid', 'Выкуплена'),
        ('cancelled', 'Отменена'),
        ('expired', 'Истекла'),
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Пользователь")
    session = models.ForeignKey(Session, on_delete=models.CASCADE, verbose_name="Сеанс")
    seat = models.ForeignKey(Seat, on_delete=models.CASCADE, verbose_name="Место")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='held', verbose_name="Статус")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создана")
    expires_at = models.DateTimeField(verbose_name="Удерживается до")

    class Meta:
        verbose_name = "Бронь"
        verbose_name_plural = "Брони"

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(minutes=15)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Бронь #{self.id} - {self.user.username}"


class Ticket(models.Model):
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, verbose_name="Бронь")
    number = models.CharField(max_length=20, unique=True, verbose_name="Номер билета")
    price = models.DecimalField(max_digits=8, decimal_places=2, verbose_name="Цена")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Выкуплен")

    class Meta:
        verbose_name = "Билет"
        verbose_name_plural = "Билеты"

    def __str__(self):
        return f"Билет {self.number}"


class Review(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Автор")
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="reviews", verbose_name="Фильм")
    rating = models.PositiveIntegerField(default=5, verbose_name="Оценка")
    text = models.TextField(verbose_name="Текст отзыва")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")

    class Meta:
        verbose_name = "Отзыв"
        verbose_name_plural = "Отзывы"

    def __str__(self):
        return f"{self.user.username} → {self.movie.title}"