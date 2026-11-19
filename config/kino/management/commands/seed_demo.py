"""Загрузка демонстрационных данных: python manage.py seed_demo [--clear]."""
from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import get_random_string

from kino.demo_data import build, seat_category
from kino.models import (
    Booking,
    Genre,
    Hall,
    Movie,
    Review,
    Seat,
    Session,
    SessionPrice,
    Ticket,
)


class Command(BaseCommand):
    help = "Загружает демонстрационные данные кинотеатра"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="удалить данные кинотеатра и демо-пользователей перед загрузкой",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["clear"]:
            self.clear()
        elif Movie.objects.exists():
            self.stdout.write(self.style.WARNING(
                "В базе уже есть фильмы. Для полной перезагрузки используйте --clear."
            ))
            return

        now_local = timezone.localtime().replace(tzinfo=None, microsecond=0)
        data = build(now_local)
        self.check_user_conflicts(data["users"])

        demo_password = get_random_string(24)
        cashier_group, _ = Group.objects.get_or_create(name="Кассир")
        genres = {name: Genre.objects.create(name=name) for name in data["genres"]}

        movies = []
        for title, description, duration, year, age, genre_names in data["movies"]:
            movie = Movie.objects.create(
                title=title,
                description=description,
                duration_min=duration,
                year=year,
                age_limit=age,
            )
            movie.genres.set([genres[name] for name in genre_names])
            movies.append(movie)

        halls = []
        seats = {}
        for name, rows, per_row in data["halls"]:
            hall = Hall.objects.create(
                name=name,
                rows_count=rows,
                seats_per_row=per_row,
            )
            halls.append(hall)
            Seat.objects.bulk_create([
                Seat(
                    hall=hall,
                    row=row,
                    number=number,
                    category=seat_category(row, rows),
                )
                for row in range(1, rows + 1)
                for number in range(1, per_row + 1)
            ])
            for seat in Seat.objects.filter(hall=hall):
                seats[(hall.pk, seat.row, seat.number)] = seat

        users = {}
        created_users = []
        for record in data["users"]:
            user = User.objects.filter(username=record["username"]).first()
            if user is None:
                if record["role"] == "admin":
                    user = User.objects.create_superuser(
                        username=record["username"],
                        email=record["email"],
                        password=demo_password,
                    )
                else:
                    user = User.objects.create_user(
                        username=record["username"],
                        email=record["email"],
                        password=demo_password,
                    )
                created_users.append(record["username"])
                user.first_name = record["first_name"]
                user.last_name = record["last_name"]
                user.save()
            if record["role"] == "cashier":
                user.groups.add(cashier_group)
            users[record["username"]] = user

        sessions = []
        for record in data["sessions"]:
            session = Session.objects.create(
                movie=movies[record["movie_idx"]],
                hall=halls[record["hall_idx"]],
                starts_at=timezone.make_aware(record["starts_at"]),
            )
            SessionPrice.objects.bulk_create([
                SessionPrice(session=session, category=category, price=price)
                for category, price in record["prices"].items()
            ])
            sessions.append(session)

        for record in data["bookings"]:
            hall = halls[record["hall_idx"]]
            booking = Booking.objects.create(
                user=users[record["username"]],
                session=sessions[record["session_idx"]],
                seat=seats[(hall.pk, record["row"], record["number"])],
                status=record["status"],
                created_at=timezone.make_aware(record["created_at"]),
                expires_at=timezone.make_aware(record["expires_at"]),
            )
            ticket = record["ticket"]
            if ticket:
                Ticket.objects.create(
                    booking=booking,
                    number=ticket["number"],
                    price=ticket["price"],
                    channel=ticket["channel"],
                    issued_by=users[ticket["issued_by"]] if ticket["issued_by"] else None,
                    issued_at=timezone.make_aware(ticket["issued_at"]),
                )

        for record in data["reviews"]:
            Review.objects.create(
                user=users[record["username"]],
                movie=movies[record["movie_idx"]],
                rating=record["rating"],
                text=record["text"],
                created_at=timezone.make_aware(record["created_at"]),
            )

        counts = (
            f"жанров {Genre.objects.count()}, фильмов {Movie.objects.count()}, "
            f"залов {Hall.objects.count()}, мест {Seat.objects.count()}, "
            f"сеансов {Session.objects.count()}, броней {Booking.objects.count()}, "
            f"билетов {Ticket.objects.count()}, отзывов {Review.objects.count()}."
        )
        if created_users:
            password_message = (
                f" Пароль новых демо-пользователей: {demo_password}."
            )
        else:
            password_message = " Существующие учётные записи не изменены."
        self.stdout.write(self.style.SUCCESS(f"Готово: {counts}{password_message}"))

    def check_user_conflicts(self, demo_users):
        for record in demo_users:
            user = User.objects.filter(username=record["username"]).first()
            if user is None:
                continue
            if (
                record["role"] == "admin"
                and user.is_active
                and user.is_staff
                and user.is_superuser
            ):
                continue
            raise CommandError(
                f"Имя пользователя {record['username']!r} уже занято. "
                "Измените демоданные или используйте --clear."
            )

    def clear(self):
        for model in (
            Review,
            Ticket,
            Booking,
            SessionPrice,
            Session,
            Seat,
            Hall,
            Movie,
            Genre,
        ):
            model.objects.all().delete()
        User.objects.filter(username__in=["admin", "kassir1", "kassir2"]).delete()
        User.objects.filter(username__regex=r"^user[0-9]{2}$").delete()
