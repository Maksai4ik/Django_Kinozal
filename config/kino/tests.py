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

        self.assertTrue(form.fields["email"].required)
        self.assertEqual(form.fields["password1"].label, "Пароль")
        self.assertEqual(
            form.fields["password2"].label,
            "Подтверждение пароля",
        )
        for field_name in ("username", "password1", "password2"):
            self.assertEqual(form.fields[field_name].help_text, "")


class AccountTests(TestCase):
    def test_registration_requires_and_saves_email(self):
        registration = {
            "username": "new_viewer",
            "password1": "StrongTestPassword123!",
            "password2": "StrongTestPassword123!",
        }
        response = self.client.post(reverse("register"), registration)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="new_viewer").exists())

        registration["email"] = "viewer@example.com"
        response = self.client.post(reverse("register"), registration)

        self.assertRedirects(response, reverse("index"))
        user = User.objects.get(username="new_viewer")
        self.assertEqual(user.email, "viewer@example.com")

    def test_password_change_requires_old_password_and_keeps_user_signed_in(self):
        old_password = "StrongTestPassword123!"
        new_password = "AnotherStrongPassword456!"
        user = User.objects.create_user(
            username="password_viewer",
            email="viewer@example.com",
            password=old_password,
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("password_change"),
            {
                "old_password": "incorrect",
                "new_password1": new_password,
                "new_password2": new_password,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("old_password", response.context["form"].errors)
        user.refresh_from_db()
        self.assertTrue(user.check_password(old_password))

        response = self.client.post(
            reverse("password_change"),
            {
                "old_password": old_password,
                "new_password1": new_password,
                "new_password2": new_password,
            },
        )
        self.assertRedirects(response, reverse("profile"))
        user.refresh_from_db()
        self.assertTrue(user.check_password(new_password))
        self.assertEqual(self.client.get(reverse("profile")).status_code, 200)

    def test_profile_cannot_clear_required_email(self):
        user = User.objects.create_user(
            username="profile_viewer",
            email="viewer@example.com",
            password="StrongTestPassword123!",
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("profile"),
            {
                "username": user.username,
                "first_name": "",
                "last_name": "",
                "email": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("email", response.context["form"].errors)
        user.refresh_from_db()
        self.assertEqual(user.email, "viewer@example.com")


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
        self.assertEqual(
            [showing["movie"] for showing in response.context["showings"]],
            [self.drama_movie, self.comedy_movie],
        )

    def test_genre_filter_limits_movies(self):
        response = self.client.get(
            reverse("index"),
            {"genre": self.drama.pk},
        )

        self.assertContains(response, self.drama_movie.title)
        self.assertNotContains(response, self.comedy_movie.title)
        self.assertEqual(len(response.context["showings"]), 1)

    def test_title_search_limits_movies(self):
        response = self.client.get(reverse("index"), {"q": "драма"})

        self.assertContains(response, self.drama_movie.title)
        self.assertNotContains(response, self.comedy_movie.title)
        self.assertEqual(len(response.context["showings"]), 1)

    def test_hall_filter_limits_movies(self):
        other_hall = Hall.objects.create(
            name="Другой зал",
            rows_count=5,
            seats_per_row=8,
        )
        Session.objects.create(
            movie=self.drama_movie,
            hall=other_hall,
            starts_at=self.starts_at + timedelta(minutes=45),
        )

        response = self.client.get(
            reverse("index"),
            {"hall": other_hall.pk},
        )

        self.assertContains(response, self.drama_movie.title)
        self.assertNotContains(response, self.comedy_movie.title)
        self.assertEqual(len(response.context["showings"]), 1)

    def test_title_sort_orders_movie_cards(self):
        response = self.client.get(reverse("index"), {"sort": "title"})

        titles = [showing["movie"].title for showing in response.context["showings"]]

        self.assertEqual(titles, sorted(titles))

    def test_hall_sort_orders_movie_cards_by_hall_name(self):
        first_hall = Hall.objects.create(
            name="А зал",
            rows_count=5,
            seats_per_row=8,
        )
        first_movie = self.create_movie("Фильм в первом зале", self.drama)
        Session.objects.create(
            movie=first_movie,
            hall=first_hall,
            starts_at=self.starts_at,
        )

        response = self.client.get(reverse("index"), {"sort": "hall"})

        titles = [showing["movie"].title for showing in response.context["showings"]]

        self.assertEqual(titles[0], first_movie.title)

    def test_pagination_limits_cards_and_preserves_filters(self):
        for number in range(21):
            movie = self.create_movie(f"Дополнительный фильм {number:02d}", self.drama)
            Session.objects.create(
                movie=movie,
                hall=self.hall,
                starts_at=self.starts_at + timedelta(minutes=number + 60),
            )

        first_page = self.client.get(
            reverse("index"),
            {"sort": "title", "q": "Доп"},
        )
        self.assertEqual(len(first_page.context["showings"]), 20)
        self.assertContains(
            first_page,
            "sort=title&amp;q=%D0%94%D0%BE%D0%BF&amp;page=2",
        )

        second_page = self.client.get(
            reverse("index"),
            {"sort": "title", "q": "Доп", "page": 2},
        )
        self.assertEqual(len(second_page.context["showings"]), 1)
        self.assertContains(
            second_page,
            "sort=title&amp;q=%D0%94%D0%BE%D0%BF&amp;page=1",
        )

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

    def test_my_bookings_shows_a_countdown_for_active_holds(self):
        response = self.client.get(reverse("my_bookings"))

        self.assertContains(response, "data-booking-timer")
        self.assertContains(response, "data-server-now=")

    def test_my_bookings_marks_expired_holds_as_expired(self):
        now = timezone.now()
        self.booking.created_at = now - timedelta(minutes=20)
        self.booking.expires_at = now - timedelta(minutes=5)
        self.booking.save(update_fields=["created_at", "expires_at"])

        self.client.get(reverse("my_bookings"))

        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.EXPIRED)

    def test_expired_hold_cannot_be_cancelled(self):
        now = timezone.now()
        self.booking.created_at = now - timedelta(minutes=20)
        self.booking.expires_at = now - timedelta(minutes=5)
        self.booking.save(update_fields=["created_at", "expires_at"])

        self.client.post(reverse("cancel_booking", args=[self.booking.pk]))

        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.EXPIRED)

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

    def test_session_that_has_started_cannot_be_booked(self):
        self.session.starts_at = timezone.now() - timedelta(seconds=1)
        self.session.save(update_fields=["starts_at"])

        self.client.post(
            reverse("book_seats", args=[self.session.pk]),
            {"seats": [self.seats[0].pk]},
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
