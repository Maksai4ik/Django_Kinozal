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

    def test_cashier_payment_records_channel_and_cashier(self):
        cashier = User.objects.create_user(
            username="cashier",
            password="StrongTestPassword123!",
            is_staff=True,
        )
        self.client.force_login(cashier)

        response = self.client.post(
            reverse("pay_booking", args=[self.booking.pk]),
            {"channel": Ticket.Channel.CASHBOX},
        )

        self.assertRedirects(
            response,
            reverse("cashier_bookings"),
            fetch_redirect_response=False,
        )
        ticket = Ticket.objects.get(booking=self.booking)
        self.assertEqual(ticket.channel, Ticket.Channel.CASHBOX)
        self.assertEqual(ticket.issued_by, cashier)

    def test_regular_user_cannot_issue_cashbox_ticket(self):
        response = self.client.post(
            reverse("pay_booking", args=[self.booking.pk]),
            {"channel": Ticket.Channel.CASHBOX},
        )

        self.assertRedirects(
            response,
            reverse("my_bookings"),
            fetch_redirect_response=False,
        )
        self.assertFalse(Ticket.objects.filter(booking=self.booking).exists())
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.HELD)

    def create_paid_ticket(self):
        self.booking.status = Booking.Status.PAID
        self.booking.save()
        return Ticket.objects.create(
            booking=self.booking,
            number=f"TKT-{self.booking.pk}-TEST01",
            price=self.price.price,
        )

    def test_booking_owner_can_open_printable_ticket(self):
        ticket = self.create_paid_ticket()

        response = self.client.get(
            reverse("ticket_detail", args=[ticket.pk]),
        )

        self.assertContains(response, ticket.number)
        self.assertContains(response, "Распечатать билет")

    def test_other_user_cannot_open_ticket(self):
        ticket = self.create_paid_ticket()
        other_user = User.objects.create_user(username="other")
        self.client.force_login(other_user)

        response = self.client.get(
            reverse("ticket_detail", args=[ticket.pk]),
        )

        self.assertEqual(response.status_code, 404)

    def test_cashier_can_search_by_booking_number(self):
        cashier = User.objects.create_user(
            username="cashier",
            password="StrongTestPassword123!",
            is_staff=True,
        )
        self.client.force_login(cashier)

        response = self.client.get(
            reverse("cashier_bookings"),
            {"q": str(self.booking.pk)},
        )

        self.assertContains(response, f"Бронь №{self.booking.pk}")
        self.assertContains(response, self.movie.title)


class SeatBookingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="viewer")
        self.other_user = User.objects.create_user(username="another-viewer")
        self.hall = Hall.objects.create(
            name="Зал бронирования",
            rows_count=5,
            seats_per_row=8,
        )
        self.seats = [
            Seat.objects.create(hall=self.hall, row=1, number=number)
            for number in range(1, 6)
        ]
        self.movie = Movie.objects.create(
            title="Фильм для бронирования",
            duration_min=90,
            year=2026,
        )
        self.session = Session.objects.create(
            movie=self.movie,
            hall=self.hall,
            starts_at=timezone.now() + timedelta(days=1),
        )
        self.client.force_login(self.user)

    def test_session_page_renders_multi_seat_form(self):
        response = self.client.get(
            reverse("session_detail", args=[self.session.pk]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f'action="{reverse("book_seats", args=[self.session.pk])}"',
        )
        self.assertContains(response, 'type="checkbox"', count=5)
        self.assertContains(response, 'data-hold-minutes="15"')

    def test_four_seats_are_held_in_one_submission(self):
        response = self.client.post(
            reverse("book_seats", args=[self.session.pk]),
            {"seats": [seat.pk for seat in self.seats[:4]]},
        )

        self.assertRedirects(
            response,
            reverse("session_detail", args=[self.session.pk]),
            fetch_redirect_response=False,
        )
        bookings = Booking.objects.filter(
            user=self.user,
            session=self.session,
        )
        self.assertEqual(bookings.count(), 4)
        self.assertEqual(
            set(bookings.values_list("seat_id", flat=True)),
            {seat.pk for seat in self.seats[:4]},
        )
        self.assertEqual(
            set(bookings.values_list("status", flat=True)),
            {Booking.Status.HELD},
        )
        self.assertEqual(
            len(set(bookings.values_list("expires_at", flat=True))),
            1,
        )

    def test_more_than_four_seats_are_rejected(self):
        response = self.client.post(
            reverse("book_seats", args=[self.session.pk]),
            {"seats": [seat.pk for seat in self.seats]},
        )

        self.assertRedirects(
            response,
            reverse("session_detail", args=[self.session.pk]),
            fetch_redirect_response=False,
        )
        self.assertFalse(Booking.objects.filter(session=self.session).exists())

    def test_conflict_does_not_partially_book_selected_seats(self):
        Booking.objects.create(
            user=self.other_user,
            session=self.session,
            seat=self.seats[1],
            expires_at=timezone.now() + timedelta(minutes=15),
        )

        self.client.post(
            reverse("book_seats", args=[self.session.pk]),
            {"seats": [self.seats[0].pk, self.seats[1].pk]},
        )

        self.assertEqual(
            list(
                Booking.objects.filter(session=self.session)
                .values_list("seat_id", flat=True)
            ),
            [self.seats[1].pk],
        )

    def test_availability_reports_free_held_sold_and_own_seats(self):
        now = timezone.now()
        Booking.objects.create(
            user=self.user,
            session=self.session,
            seat=self.seats[0],
            expires_at=now + timedelta(minutes=15),
        )
        Booking.objects.create(
            user=self.other_user,
            session=self.session,
            seat=self.seats[1],
            expires_at=now + timedelta(minutes=15),
        )
        Booking.objects.create(
            user=self.other_user,
            session=self.session,
            seat=self.seats[2],
            status=Booking.Status.PAID,
            expires_at=now + timedelta(minutes=15),
        )
        Booking.objects.create(
            user=self.other_user,
            session=self.session,
            seat=self.seats[3],
            created_at=now - timedelta(minutes=20),
            expires_at=now - timedelta(minutes=5),
        )

        response = self.client.get(
            reverse("session_seat_availability", args=[self.session.pk]),
        )

        self.assertEqual(response.status_code, 200)
        states = response.json()["seats"]
        self.assertEqual(states[str(self.seats[0].pk)], "mine")
        self.assertEqual(states[str(self.seats[1].pk)], "held")
        self.assertEqual(states[str(self.seats[2].pk)], "sold")
        self.assertEqual(states[str(self.seats[3].pk)], "free")
        self.assertEqual(states[str(self.seats[4].pk)], "free")
