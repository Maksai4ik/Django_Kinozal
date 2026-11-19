from datetime import timedelta
import uuid

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import ProfileForm, RegisterForm
from .models import Booking, Seat, Session, SessionPrice, Ticket
from .permissions import is_staff_or_cashier

from django.db.models import Avg
from .forms import ProfileForm, RegisterForm, ReviewForm
from .models import Booking, Movie, Review, Seat, Session, SessionPrice, Ticket

def index(request):
    # Берём только те сеансы, которые ещё не начались
    sessions = Session.objects.filter(starts_at__gte=timezone.now()).order_by("starts_at")
    return render(request, "index.html", {"sessions": sessions})


def register(request):
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Регистрация прошла успешно!")
            return redirect("index")
    else:
        form = RegisterForm()
    return render(request, "registration/register.html", {"form": form})


@login_required
def profile(request):
    if request.method == "POST":
        form = ProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Профиль обновлён")
            return redirect("profile")
    else:
        form = ProfileForm(instance=request.user)
    return render(request, "registration/profile.html", {"form": form})


def session_detail(request, pk):
    now = timezone.now()

    # Берём сеанс вместе с фильмом и залом одним запросом, чтобы не делать лишних обращений к базе
    session = get_object_or_404(
        Session.objects.select_related("movie", "hall"),
        pk=pk,
    )

    # Все места в зале, отсортированные по ряду и номеру
    seats = session.hall.seats.order_by("row", "number")

    # Цены этого сеанса по категориям мест
    prices_by_category = {
        item.category: item.price
        for item in session.prices.all()
    }

    # Собираем номера мест, которые сейчас заняты на этом сеансе:
    # либо бронь уже оплачена, либо бронь удерживается и время удержания ещё не вышло
    busy_seat_ids = set(
        Booking.objects.filter(session=session)
        .filter(
            Q(status=Booking.Status.PAID)
            | Q(status=Booking.Status.HELD, expires_at__gt=now)
        )
        .values_list("seat_id", flat=True)
    )

    # Группируем места по рядам для удобного вывода в шаблоне
    rows_map = {}
    for seat in seats:
        rows_map.setdefault(seat.row, []).append({
            "seat": seat,
            "is_busy": seat.id in busy_seat_ids,
            "price": prices_by_category.get(seat.category),
        })

    rows = sorted(rows_map.items(), key=lambda item: item[0])

    return render(
        request,
        "session_detail.html",
        {
            "session": session,
            "rows": rows,
            "prices_by_category": prices_by_category,
            "busy_seat_ids": busy_seat_ids,
        },
    )


@login_required
def book_seat(request, session_id, seat_id):
    # Изменять базу данных нужно только при отправке формы, а не при простом открытии ссылки
    if request.method != "POST":
        return redirect("session_detail", pk=session_id)

    now = timezone.now()

    # Открываем транзакцию: проверка и создание брони идут как единое целое
    with transaction.atomic():
        # Блокируем строку сеанса в базе, чтобы два человека не забрали место в одну секунду
        session = get_object_or_404(
            Session.objects.select_for_update().select_related("movie", "hall"),
            pk=session_id,
        )

        # Проверяем, что сеанс не отменён и ещё не начался
        if session.status != Session.Status.ACTIVE:
            messages.error(request, "Сеанс отменён, забронировать место нельзя.")
            return redirect("session_detail", pk=session.pk)

        if session.starts_at <= now:
            messages.error(request, "Сеанс уже начался.")
            return redirect("session_detail", pk=session.pk)

        # Находим место и проверяем, что оно действительно из зала этого сеанса
        seat = get_object_or_404(Seat, pk=seat_id, hall=session.hall)

        # Помечаем истёкшими старые удержания, у которых время удержания уже вышло
        Booking.objects.filter(
            session=session,
            seat=seat,
            status=Booking.Status.HELD,
            expires_at__lte=now,
        ).update(status=Booking.Status.EXPIRED)

        # Проверяем, не занято ли место сейчас (уже выкуплено или ещё удерживается)
        already_taken = (
            Booking.objects.filter(session=session, seat=seat)
            .filter(
                Q(status=Booking.Status.PAID)
                | Q(status=Booking.Status.HELD, expires_at__gt=now)
            )
            .exists()
        )

        if already_taken:
            messages.error(request, "Это место уже занято.")
            return redirect("session_detail", pk=session.pk)

        # Вычисляем момент окончания удержания: сейчас + заданное число минут удержания
        expires_at = now + timedelta(minutes=Booking.HOLD_MINUTES)

        try:
            # Записываем новую бронь в таблицу броней
            Booking.objects.create(
                user=request.user,
                session=session,
                seat=seat,
                created_at=now,
                expires_at=expires_at,
                status=Booking.Status.HELD,
            )
        except IntegrityError:
            # Перехватываем срабатывание ограничения уникальности в самой базе данных
            messages.error(request, "Место только что забронировал кто-то другой.")
            return redirect("session_detail", pk=session.pk)

    messages.success(
        request,
        f"Место (ряд {seat.row}, место {seat.number}) забронировано на {Booking.HOLD_MINUTES} мин.",
    )
    return redirect("session_detail", pk=session.pk)


@login_required
def my_bookings(request):
    # Берём только брони текущего пользователя, сразу подтягивая связанные данные
    bookings = (
        Booking.objects.filter(user=request.user)
        .select_related("session__movie", "session__hall", "seat", "ticket")
        .order_by("-created_at")
    )
    return render(request, "my_bookings.html", {"bookings": bookings})


@login_required
def cancel_booking(request, pk):
    if request.method != "POST":
        return redirect("my_bookings")

    booking = get_object_or_404(
        Booking.objects.select_related("user", "seat", "session"),
        pk=pk,
    )

    is_owner = booking.user_id == request.user.id
    if not (is_owner or is_staff_or_cashier(request.user)):
        messages.error(request, "У вас нет прав на отмену этой брони.")
        return redirect("my_bookings")

    # Отменить можно только бронь, которая сейчас удерживается
    if booking.status != Booking.Status.HELD:
        messages.error(request, "Отменить можно только активную удержанную бронь.")
        return redirect("my_bookings")

    if booking.session.starts_at <= timezone.now():
        messages.error(request, "Отменить бронь можно только до начала сеанса.")
        return redirect("my_bookings")

    booking.status = Booking.Status.CANCELLED
    booking.save()
    messages.success(
        request,
        f"Бронь на место (ряд {booking.seat.row}, место {booking.seat.number}) отменена.",
    )
    return redirect("my_bookings")


@login_required
def pay_booking(request, pk):
    if request.method != "POST":
        return redirect("my_bookings")

    now = timezone.now()

    with transaction.atomic():
        booking = get_object_or_404(
            Booking.objects.select_for_update().select_related(
                "user", "session", "seat", "ticket"
            ),
            pk=pk,
        )

        is_owner = booking.user_id == request.user.id
        if not (is_owner or is_staff_or_cashier(request.user)):
            messages.error(request, "У вас нет прав на выкуп этой брони.")
            return redirect("my_bookings")

        if booking.status == Booking.Status.PAID or hasattr(booking, "ticket"):
            messages.info(request, "Эта бронь уже выкуплена.")
            return redirect("my_bookings")

        if booking.status != Booking.Status.HELD:
            messages.error(request, "Эту бронь нельзя выкупить (она отменена или неактивна).")
            return redirect("my_bookings")

        if booking.expires_at and booking.expires_at <= now:
            booking.status = Booking.Status.EXPIRED
            booking.save()
            messages.error(request, "Время удержания брони истекло, место освободилось.")
            return redirect("my_bookings")

        session_price = SessionPrice.objects.filter(
            session=booking.session,
            category=booking.seat.category,
        ).first()

        if not session_price:
            messages.error(request, "Для этого сеанса и категории места не задана цена.")
            return redirect("my_bookings")

        for _ in range(5):
            ticket_number = f"TKT-{booking.id}-{uuid.uuid4().hex[:6].upper()}"
            try:
                Ticket.objects.create(
                    booking=booking,
                    number=ticket_number,
                    price=session_price.price,
                    purchased_at=now,
                )
                break
            except IntegrityError:
                ticket_number = None

        if not ticket_number:
            messages.error(request, "Не удалось сформировать уникальный номер билета, попробуйте ещё раз.")
            return redirect("my_bookings")

        booking.status = Booking.Status.PAID
        booking.expires_at = None
        booking.save()

    messages.success(
        request,
        f"Билет {ticket_number} успешно оформлен! Стоимость: {session_price.price} ₽.",
    )
    return redirect("my_bookings")

 def movie_detail(request, pk):
    movie = get_object_or_404(Movie, pk=pk)

    # Ближайшие сеансы этого фильма, которые ещё не начались
    upcoming_sessions = (
        Session.objects.filter(movie=movie, starts_at__gte=timezone.now())
        .select_related("hall")
        .order_by("starts_at")
    )

    # Все отзывы по фильму вместе с авторами, от свежих к старым
    reviews = (
        Review.objects.filter(movie=movie)
        .select_related("user")
        .order_by("-created_at")
    )

    # Средняя оценка фильма по всем отзывам (вернёт словарь, например {'avg_rating': 4.5} или None)
    avg_rating = reviews.aggregate(avg_rating=Avg("rating"))["avg_rating"]

    if request.method == "POST":
        if not request.user.is_authenticated:
            messages.error(request, "Чтобы оставить отзыв, войдите в аккаунт.")
            return redirect("login")

        form = ReviewForm(request.POST)
        if form.is_valid():
            # Сначала создаём объект отзыва в памяти, чтобы подставить автора и фильм
            review = form.save(commit=False)
            review.user = request.user
            review.movie = movie
            review.save()
            messages.success(request, "Спасибо! Ваш отзыв добавлен.")
            return redirect("movie_detail", pk=movie.pk)
    else:
        form = ReviewForm()

    return render(
        request,
        "movie_detail.html",
        {
            "movie": movie,
            "upcoming_sessions": upcoming_sessions,
            "reviews": reviews,
            "avg_rating": avg_rating,
            "form": form,
        },
    )

@login_required
def cashier_bookings(request):
    if not is_staff_or_cashier(request.user):
        messages.error(request, "Доступ к служебной странице есть только у кассиров и сотрудников.")
        return redirect("index")

    selected_session_id = request.GET.get("session", "").strip()
    search_query = request.GET.get("q", "").strip()

    bookings = (
        Booking.objects.select_related(
            "user", "session__movie", "session__hall", "seat", "ticket"
        )
        .order_by("-created_at")
    )

    if selected_session_id.isdigit():
        bookings = bookings.filter(session_id=int(selected_session_id))

    if search_query:
        bookings = bookings.filter(
            Q(user__username__icontains=search_query)
            | Q(ticket__number__icontains=search_query)
        )

    sessions = (
        Session.objects.select_related("movie", "hall")
        .order_by("-starts_at")
    )

    return render(
        request,
        "cashier_bookings.html",
        {
            "bookings": bookings,
            "sessions": sessions,
            "selected_session_id": selected_session_id,
            "search_query": search_query,
        },
    )