"""Модели приложения cinema: киноафиша с бронированием мест.

Пользователь — стандартная модель django.contrib.auth.User.
Роли: группа «Кассир»; администратор — пользователь с is_staff=True.
"""
from datetime import timedelta

from django.conf import settings
from django.core.validators import MaxLengthValidator, MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.templatetags.static import static
from django.utils import timezone


def check_constraint(condition, name):
    """CheckConstraint, работающий и в Django 4.2 (check=), и в 5.1+ (condition=)."""
    try:
        return models.CheckConstraint(condition=condition, name=name)
    except TypeError:
        return models.CheckConstraint(check=condition, name=name)


class SeatCategory(models.TextChoices):
    STANDARD = "standard", "Обычное"
    VIP = "vip", "VIP"


class Genre(models.Model):
    name = models.CharField("название", max_length=50, unique=True)

    class Meta:
        verbose_name = "жанр"
        verbose_name_plural = "жанры"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Movie(models.Model):
    AGE_CHOICES = [(0, "0+"), (6, "6+"), (12, "12+"), (16, "16+"), (18, "18+")]

    title = models.CharField("название", max_length=200)
    description = models.TextField("описание", blank=True)
    duration_min = models.PositiveSmallIntegerField(
        "длительность, мин", validators=[MinValueValidator(1), MaxValueValidator(600)])
    year = models.PositiveSmallIntegerField(
        "год выпуска", validators=[MinValueValidator(1900), MaxValueValidator(2100)])
    age_limit = models.PositiveSmallIntegerField("возрастное ограничение", choices=AGE_CHOICES, default=0)
    poster = models.ImageField("постер", upload_to="posters/", blank=True)
    backdrop = models.ImageField("фоновое изображение", upload_to="backdrops/", blank=True)
    is_active = models.BooleanField("показывать в афише", default=True)
    genres = models.ManyToManyField(Genre, related_name="movies", verbose_name="жанры", blank=True)
    created_at = models.DateTimeField("создан", default=timezone.now, editable=False)

    class Meta:
        verbose_name = "фильм"
        verbose_name_plural = "фильмы"
        ordering = ["title"]
        constraints = [
            check_constraint(Q(duration_min__gte=1, duration_min__lte=600), "movie_duration_range"),
            check_constraint(Q(age_limit__in=[0, 6, 12, 16, 18]), "movie_age_limit_values"),
        ]

    def __str__(self):
        return f"{self.title} ({self.year})"

    @property
    def poster_url(self):
        """Адрес постера или картинка-заглушка."""
        return self.poster.url if self.poster else static("img/poster_placeholder.svg")

    @property
    def duration_text(self):
        hours, minutes = divmod(self.duration_min, 60)
        return f"{hours} ч {minutes:02d} мин" if hours else f"{minutes} мин"


class Hall(models.Model):
    name = models.CharField("название", max_length=50, unique=True)
    rows_count = models.PositiveSmallIntegerField(
        "число рядов", validators=[MinValueValidator(1), MaxValueValidator(30)])
    seats_per_row = models.PositiveSmallIntegerField(
        "мест в ряду", validators=[MinValueValidator(1), MaxValueValidator(40)])
    description = models.CharField("описание", max_length=200, blank=True)

    class Meta:
        verbose_name = "зал"
        verbose_name_plural = "залы"
        ordering = ["name"]
        constraints = [
            check_constraint(Q(rows_count__gte=1, rows_count__lte=30), "hall_rows_range"),
            check_constraint(Q(seats_per_row__gte=1, seats_per_row__lte=40), "hall_seats_range"),
        ]

    def __str__(self):
        return self.name

    @property
    def total_seats(self):
        return self.rows_count * self.seats_per_row


class Seat(models.Model):
    hall = models.ForeignKey(Hall, on_delete=models.CASCADE, related_name="seats", verbose_name="зал")
    row = models.PositiveSmallIntegerField("ряд", validators=[MinValueValidator(1)])
    number = models.PositiveSmallIntegerField("номер места", validators=[MinValueValidator(1)])
    category = models.CharField("категория", max_length=10, choices=SeatCategory.choices,
                                default=SeatCategory.STANDARD)

    class Meta:
        verbose_name = "место"
        verbose_name_plural = "места"
        ordering = ["hall", "row", "number"]
        constraints = [
            models.UniqueConstraint(fields=["hall", "row", "number"], name="uniq_seat_position"),
            check_constraint(Q(row__gte=1, number__gte=1), "seat_positive_position"),
        ]

    def __str__(self):
        return f"{self.hall}: ряд {self.row}, место {self.number}"


class Session(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Идёт по расписанию"
        CANCELLED = "cancelled", "Отменён"

    movie = models.ForeignKey(Movie, on_delete=models.PROTECT, related_name="sessions", verbose_name="фильм")
    hall = models.ForeignKey(Hall, on_delete=models.PROTECT, related_name="sessions", verbose_name="зал")
    starts_at = models.DateTimeField("начало", db_index=True)
    status = models.CharField("статус", max_length=10, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField("создан", default=timezone.now, editable=False)

    class Meta:
        verbose_name = "сеанс"
        verbose_name_plural = "сеансы"
        ordering = ["starts_at"]
        indexes = [models.Index(fields=["hall", "starts_at"], name="session_hall_start_idx")]

    def __str__(self):
        return f"{self.movie.title}, {self.hall}, {timezone.localtime(self.starts_at):%d.%m.%Y %H:%M}"

    @property
    def ends_at(self):
        return self.starts_at + timedelta(minutes=self.movie.duration_min)


class SessionPrice(models.Model):
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name="prices", verbose_name="сеанс")
    category = models.CharField("категория места", max_length=10, choices=SeatCategory.choices)
    price = models.DecimalField("цена, руб.", max_digits=8, decimal_places=2,
                                validators=[MinValueValidator(0)])

    class Meta:
        verbose_name = "цена по категории"
        verbose_name_plural = "цены по категориям"
        ordering = ["session", "category"]
        constraints = [
            models.UniqueConstraint(fields=["session", "category"], name="uniq_price_per_category"),
            check_constraint(Q(price__gt=0), "sessionprice_positive"),
        ]

    def __str__(self):
        return f"{self.session}: {self.get_category_display()} — {self.price} ₽"


class Booking(models.Model):
    class Status(models.TextChoices):
        HELD = "held", "Удерживается"
        PAID = "paid", "Выкуплена"
        EXPIRED = "expired", "Истекла"
        CANCELLED = "cancelled", "Отменена"

    HOLD_MINUTES = 15
    ACTIVE_STATUSES = (Status.HELD, Status.PAID)

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                             related_name="bookings", verbose_name="пользователь")
    session = models.ForeignKey(Session, on_delete=models.PROTECT, related_name="bookings", verbose_name="сеанс")
    seat = models.ForeignKey(Seat, on_delete=models.PROTECT, related_name="bookings", verbose_name="место")
    created_at = models.DateTimeField("создана", default=timezone.now, editable=False)
    expires_at = models.DateTimeField("удерживается до")
    status = models.CharField("статус", max_length=10, choices=Status.choices, default=Status.HELD)

    class Meta:
        verbose_name = "бронь"
        verbose_name_plural = "брони"
        ordering = ["-created_at"]
        constraints = [
            # одно место на сеансе не может иметь двух активных броней
            models.UniqueConstraint(fields=["session", "seat"],
                                    condition=Q(status__in=["held", "paid"]),
                                    name="uniq_active_booking_per_seat"),
            check_constraint(Q(expires_at__gt=F("created_at")), "booking_expires_after_created"),
        ]
        indexes = [models.Index(fields=["session", "status"], name="booking_session_status_idx")]

    def __str__(self):
        return f"Бронь №{self.pk}: {self.user}, {self.seat}"

    def is_active(self, now=None):
        """Бронь занимает место: выкуплена либо удерживается и срок не истёк."""
        now = now or timezone.now()
        if self.status == self.Status.PAID:
            return True
        return self.status == self.Status.HELD and self.expires_at > now

    @classmethod
    def expire_due(cls, now=None):
        now = now or timezone.now()
        return cls.objects.filter(
            status=cls.Status.HELD,
            expires_at__lte=now,
        ).update(status=cls.Status.EXPIRED)


class Ticket(models.Model):
    class Channel(models.TextChoices):
        ONLINE = "online", "Онлайн"
        CASHBOX = "cashbox", "Касса"

    booking = models.OneToOneField(Booking, on_delete=models.PROTECT, related_name="ticket", verbose_name="бронь")
    number = models.CharField("номер билета", max_length=20, unique=True)
    price = models.DecimalField("цена, руб.", max_digits=8, decimal_places=2, validators=[MinValueValidator(0)])
    issued_at = models.DateTimeField("выкуплен", default=timezone.now, editable=False)
    channel = models.CharField("канал", max_length=10, choices=Channel.choices, default=Channel.ONLINE)
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name="issued_tickets", verbose_name="оформил (кассир)")

    class Meta:
        verbose_name = "билет"
        verbose_name_plural = "билеты"
        ordering = ["-issued_at"]
        constraints = [check_constraint(Q(price__gte=0), "ticket_price_not_negative")]

    def __str__(self):
        return f"Билет {self.number}"


class Review(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="reviews", verbose_name="автор")
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="reviews", verbose_name="фильм")
    rating = models.PositiveSmallIntegerField("оценка", validators=[MinValueValidator(1), MaxValueValidator(5)])
    text = models.TextField("текст", validators=[MaxLengthValidator(1000)])
    created_at = models.DateTimeField("создан", default=timezone.now, editable=False)
    updated_at = models.DateTimeField("изменён", auto_now=True)

    class Meta:
        verbose_name = "отзыв"
        verbose_name_plural = "отзывы"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "movie"], name="uniq_review_per_user_movie"),
            check_constraint(Q(rating__gte=1, rating__lte=5), "review_rating_range"),
        ]

    def __str__(self):
        return f"{self.user}: {self.movie.title} — {self.rating}"
