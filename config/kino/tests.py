from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import RegisterForm
from .models import (
    Booking,
    Genre,
    Hall,
    Movie,
    Seat,
    Session,
    SessionPrice,
    Ticket,
)


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


class LoginRedirectTests(TestCase):
    def test_staff_login_redirects_to_admin(self):
        User.objects.create_user(
            username="staff",
            password="StrongTestPassword123!",
            is_staff=True,
        )

        response = self.client.post(
            reverse("login"),
            {"username": "staff", "password": "StrongTestPassword123!"},
        )

        self.assertRedirects(
            response,
            reverse("admin:index"),
            fetch_redirect_response=False,
        )

    def test_regular_login_redirects_to_home(self):
        User.objects.create_user(
            username="regular",
            password="StrongTestPassword123!",
        )

        response = self.client.post(
            reverse("login"),
            {"username": "regular", "password": "StrongTestPassword123!"},
        )

        self.assertRedirects(
            response,
            reverse("index"),
            fetch_redirect_response=False,
        )


class HomePageTests(TestCase):
    def setUp(self):
        self.drama = Genre.objects.create(name="Драма")
        self.comedy = Genre.objects.create(name="Комедия")
        self.hall = Hall.objects.create(
            name="Тестовый зал",
            rows_count=5,
            seats_per_row=8,
        )
        self.starts_at = timezone.now() + timedelta(days=1)
        self.drama_movie = self.create_movie("Тестовая драма", self.drama)
        self.comedy_movie = self.create_movie("Тестовая комедия", self.comedy)
        Session.objects.create(
            movie=self.drama_movie,
            hall=self.hall,
            starts_at=self.starts_at,
        )
        Session.objects.create(
            movie=self.comedy_movie,
            hall=self.hall,
            starts_at=self.starts_at + timedelta(minutes=30),
        )

    def create_movie(self, title, genre):
        movie = Movie.objects.create(
            title=title,
            duration_min=100,
            year=2026,
        )
        movie.genres.add(genre)
        return movie

    def test_homepage_shows_upcoming_movies(self):
        response = self.client.get(reverse("index"))

        self.assertContains(response, self.drama_movie.title)
        self.assertContains(response, self.comedy_movie.title)
        self.assertEqual(len(response.context["showings"]), 2)

    def test_genre_filter_limits_movies(self):
        response = self.client.get(
            reverse("index"),
            {"genre": self.drama.pk},
        )

        self.assertContains(response, self.drama_movie.title)
        self.assertNotContains(response, self.comedy_movie.title)
        self.assertEqual(len(response.context["showings"]), 1)

    def test_movie_with_backdrop_is_featured(self):
        self.comedy_movie.backdrop.name = "backdrops/comedy.png"
        self.comedy_movie.save(update_fields=["backdrop"])

        response = self.client.get(reverse("index"))

        self.assertEqual(
            response.context["featured"]["movie"],
            self.comedy_movie,
        )

    def test_bookings_link_is_in_header_without_hero_arrows(self):
        user = User.objects.create_user(username="viewer")
        self.client.force_login(user)

        response = self.client.get(reverse("index"))

        self.assertContains(response, reverse("my_bookings"))
        self.assertNotContains(response, "Смотреть афишу")
        self.assertNotContains(response, "Афиша ↓")


class TicketPaymentTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="viewer",
            password="StrongTestPassword123!",
        )
        self.hall = Hall.objects.create(
            name="Зал выкупа",
            rows_count=5,
            seats_per_row=8,
        )
        self.seat = Seat.objects.create(
            hall=self.hall,
            row=1,
            number=1,
        )
        self.movie = Movie.objects.create(
            title="Фильм для выкупа",
            duration_min=90,
            year=2026,
        )
        self.session = Session.objects.create(
            movie=self.movie,
            hall=self.hall,
            starts_at=timezone.now() + timedelta(days=1),
        )
        self.price = SessionPrice.objects.create(
            session=self.session,
            category=self.seat.category,
            price=Decimal("10.00"),
        )
        self.booking = Booking.objects.create(
            user=self.user,
            session=self.session,
            seat=self.seat,
            expires_at=timezone.now() + timedelta(minutes=15),
        )
        self.booking_expires_at = self.booking.expires_at
        self.client.force_login(self.user)

    def test_payment_issues_ticket_and_keeps_booking_expiry(self):
        response = self.client.post(
            reverse("pay_booking", args=[self.booking.pk]),
        )

        self.assertRedirects(
            response,
            reverse("my_bookings"),
            fetch_redirect_response=False,
        )
        self.booking.refresh_from_db()
        ticket = Ticket.objects.get(booking=self.booking)

        self.assertEqual(self.booking.status, Booking.Status.PAID)
        self.assertEqual(self.booking.expires_at, self.booking_expires_at)
        self.assertEqual(ticket.price, self.price.price)
        self.assertEqual(ticket.channel, Ticket.Channel.ONLINE)
