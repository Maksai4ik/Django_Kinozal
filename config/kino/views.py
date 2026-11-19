import csv
import logging
import smtplib
import uuid
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Avg, Count, Q, Sum
from django.core.mail import send_mail
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.dateparse import parse_date
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .forms import (
    AccountPasswordChangeForm,
    ProfileForm,
    RegisterForm,
    ReviewForm,
    SalesReportPeriodForm,
)
from .models import (
    Booking,
    Genre,
    Hall,
    Movie,
    Review,
    Seat,
    Session,
    SessionPrice,
    Ticket,
    UserProfile,
)
from .permissions import is_staff_or_cashier


logger = logging.getLogger(__name__)


class StaffLoginView(LoginView):
    def get_success_url(self):
        redirect_url = self.get_redirect_url()
        if redirect_url:
            return redirect_url
        if self.request.user.is_staff:
            return reverse("admin:index")
        return super().get_success_url()


class AccountPasswordChangeView(PasswordChangeView):
    form_class = AccountPasswordChangeForm
    template_name = "password_change.html"
    success_url = reverse_lazy("profile")

    def form_valid(self, form):
        messages.success(self.request, "Пароль успешно изменён.")
        return super().form_valid(form)


def index(request):
    now = timezone.now()
    week_end = now + timedelta(days=7)
    genres = list(Genre.objects.order_by("name"))
    genre_by_id = {str(genre.pk): genre for genre in genres}
    selected_genre = genre_by_id.get(request.GET.get("genre", ""))
    halls = list(
        Hall.objects.filter(
            sessions__starts_at__gte=now,
            sessions__starts_at__lt=week_end,
            sessions__status=Session.Status.ACTIVE,
            sessions__movie__is_active=True,
        )
        .distinct()
        .order_by("name")
    )
    hall_by_id = {str(hall.pk): hall for hall in halls}
    selected_hall = hall_by_id.get(request.GET.get("hall", ""))
    search_query = request.GET.get("q", "").strip()
    sort_options = {
        "time": ("starts_at", "pk"),
        "title": ("movie__title", "starts_at", "pk"),
        "hall": ("hall__name", "starts_at", "movie__title", "pk"),
    }
    selected_sort = request.GET.get("sort", "time")
    if selected_sort not in sort_options:
        selected_sort = "time"

    sessions = (
        Session.objects.filter(
            starts_at__gte=now,
            starts_at__lt=week_end,
            status=Session.Status.ACTIVE,
            movie__is_active=True,
        )
        .select_related("movie", "hall")
        .prefetch_related("movie__genres", "prices")
    )
    if selected_genre:
        sessions = sessions.filter(movie__genres=selected_genre).distinct()
    if selected_hall:
        sessions = sessions.filter(hall=selected_hall)
    if search_query:
        sessions = sessions.filter(movie__title__icontains=search_query)

    sessions = list(sessions.order_by(*sort_options[selected_sort]))

    available_dates = sorted({
        timezone.localtime(session.starts_at).date()
        for session in sessions
    })
    requested_date = parse_date(request.GET.get("date", ""))
    selected_date = (
        requested_date
        if requested_date in available_dates
        else (available_dates[0] if available_dates else None)
    )

    showings_by_movie = {}
    if selected_date:
        for session in sessions:
            if timezone.localtime(session.starts_at).date() != selected_date:
                continue
            movie_id = session.movie_id
            if movie_id not in showings_by_movie:
                showings_by_movie[movie_id] = {
                    "movie": session.movie,
                    "sessions": [],
                }
            showings_by_movie[movie_id]["sessions"].append(session)

    weekday_names = (
        "Понедельник", "Вторник", "Среда", "Четверг",
        "Пятница", "Суббота", "Воскресенье",
    )
    today = timezone.localdate()
    date_options = [
        {
            "value": date.isoformat(),
            "label": (
                "Сегодня" if date == today
                else "Завтра" if date == today + timedelta(days=1)
                else f"{weekday_names[date.weekday()]}, {date:%d.%m}"
            ),
        }
        for date in available_dates
    ]

    all_showings = list(showings_by_movie.values())
    featured = next(
        (showing for showing in all_showings if showing["movie"].backdrop),
        all_showings[0] if all_showings else None,
    )
    page_obj = Paginator(all_showings, 20).get_page(request.GET.get("page"))
    pagination_query = request.GET.copy()
    pagination_query.pop("page", None)

    return render(
        request,
        "index.html",
        {
            "showings": page_obj.object_list,
            "page_obj": page_obj,
            "pagination_query": pagination_query.urlencode(),
            "featured": featured,
            "genres": genres,
            "halls": halls,
            "selected_hall_id": selected_hall.pk if selected_hall else None,
            "search_query": search_query,
            "selected_sort": selected_sort,
            "date_options": date_options,
            "selected_date": selected_date.isoformat() if selected_date else "",
            "selected_genre_id": selected_genre.pk if selected_genre else None,
        },
    )


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
    return render(request, "register.html", {"form": form})


def about(request):
    return render(request, "about.html")


@login_required
def profile(request):
    if request.method == "POST":
        form = ProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            user = form.save()
            UserProfile.objects.update_or_create(
                user=user,
                defaults={"phone": form.cleaned_data["phone"]},
            )
            messages.success(request, "Профиль обновлён")
            return redirect("profile")
    else:
        form = ProfileForm(instance=request.user)
    return render(request, "profile.html", {"form": form})


def _active_seat_statuses(session, now, user_id=None):
    statuses = {}
    active_bookings = (
        Booking.objects.filter(session=session)
        .filter(
            Q(status=Booking.Status.PAID)
            | Q(status=Booking.Status.HELD, expires_at__gt=now)
        )
        .values_list("seat_id", "status", "user_id")
    )
    for seat_id, status, booking_user_id in active_bookings:
        if booking_user_id == user_id and user_id is not None:
            statuses[seat_id] = "mine"
        elif status == Booking.Status.PAID:
            statuses[seat_id] = "sold"
        else:
            statuses[seat_id] = "held"
    return statuses


def _can_book_session(session, now):
    return session.status == Session.Status.ACTIVE and session.starts_at > now


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

    seat_statuses = _active_seat_statuses(
        session,
        now,
        request.user.pk if request.user.is_authenticated else None,
    )
    status_labels = {
        "free": "Свободно",
        "held": "Удерживается",
        "sold": "Выкуплено",
        "mine": "Ваша бронь",
    }

    # Группируем места по рядам для удобного вывода в шаблоне
    rows_map = {}
    for seat in seats:
        status = seat_statuses.get(seat.id, "free")
        rows_map.setdefault(seat.row, []).append({
            "seat": seat,
            "status": status,
            "status_label": status_labels[status],
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
            "can_book": _can_book_session(session, now),
            "hold_minutes": Booking.HOLD_MINUTES,
        },
    )


@require_GET
def session_seat_availability(request, pk):
    now = timezone.now()
    session = get_object_or_404(
        Session.objects.select_related("hall"),
        pk=pk,
    )
    seat_statuses = _active_seat_statuses(
        session,
        now,
        request.user.pk if request.user.is_authenticated else None,
    )
    seats = {
        str(seat_id): seat_statuses.get(seat_id, "free")
        for seat_id in session.hall.seats.values_list("pk", flat=True)
    }
    response = JsonResponse({
        "booking_open": _can_book_session(session, now),
        "seats": seats,
    })
    response["Cache-Control"] = "no-store"
    return response


def _book_selected_seats(request, session_id, seat_ids):
    if not 1 <= len(seat_ids) <= 4 or len(set(seat_ids)) != len(seat_ids):
        messages.error(request, "Выберите от 1 до 4 разных мест.")
        return redirect("session_detail", pk=session_id)

    now = timezone.now()

    with transaction.atomic():
        session = get_object_or_404(
            Session.objects.select_for_update().select_related("movie", "hall"),
            pk=session_id,
        )

        if session.status != Session.Status.ACTIVE:
            messages.error(request, "Сеанс отменён, забронировать места нельзя.")
            return redirect("session_detail", pk=session.pk)

        if session.starts_at <= now:
            messages.error(request, "Сеанс уже начался.")
            return redirect("session_detail", pk=session.pk)

        seats = list(
            Seat.objects.filter(pk__in=seat_ids, hall=session.hall)
            .order_by("row", "number")
        )
        if len(seats) != len(seat_ids):
            messages.error(request, "Выбраны недопустимые места.")
            return redirect("session_detail", pk=session.pk)

        Booking.objects.filter(
            session=session,
            seat_id__in=seat_ids,
            status=Booking.Status.HELD,
            expires_at__lte=now,
        ).update(status=Booking.Status.EXPIRED)

        already_taken = set(
            Booking.objects.filter(session=session, seat_id__in=seat_ids)
            .filter(
                Q(status=Booking.Status.PAID)
                | Q(status=Booking.Status.HELD, expires_at__gt=now)
            )
            .values_list("seat_id", flat=True)
        )
        if already_taken:
            messages.error(
                request,
                "Одно или несколько мест только что заняли. Обновите схему и выберите другие.",
            )
            return redirect("session_detail", pk=session.pk)

        expires_at = now + timedelta(minutes=Booking.HOLD_MINUTES)
        try:
            with transaction.atomic():
                Booking.objects.bulk_create([
                    Booking(
                        user=request.user,
                        session=session,
                        seat=seat,
                        created_at=now,
                        expires_at=expires_at,
                        status=Booking.Status.HELD,
                    )
                    for seat in seats
                ])
        except IntegrityError:
            messages.error(
                request,
                "Одно или несколько мест только что забронировал другой пользователь.",
            )
            return redirect("session_detail", pk=session.pk)

    places = ", ".join(
        f"ряд {seat.row}, место {seat.number}"
        for seat in seats
    )
    messages.success(
        request,
        f"Места ({places}) забронированы на {Booking.HOLD_MINUTES} мин.",
    )
    return redirect("session_detail", pk=session.pk)


@login_required
def book_seats(request, session_id):
    if request.method != "POST":
        return redirect("session_detail", pk=session_id)

    raw_seat_ids = request.POST.getlist("seats")
    if not 1 <= len(raw_seat_ids) <= 4:
        messages.error(request, "Выберите от 1 до 4 мест.")
        return redirect("session_detail", pk=session_id)

    try:
        seat_ids = [int(value) for value in raw_seat_ids]
    except ValueError:
        messages.error(request, "Выбраны недопустимые места.")
        return redirect("session_detail", pk=session_id)

    return _book_selected_seats(request, session_id, seat_ids)


@login_required
def book_seat(request, session_id, seat_id):
    if request.method != "POST":
        return redirect("session_detail", pk=session_id)

    return _book_selected_seats(request, session_id, [seat_id])


@login_required
def my_bookings(request):
    server_now = timezone.now()
    Booking.expire_due(server_now)
    # Берём только брони текущего пользователя, сразу подтягивая связанные данные
    bookings = (
        Booking.objects.filter(user=request.user)
        .select_related("session__movie", "session__hall", "seat", "ticket")
        .order_by("-created_at")
    )
    return render(
        request,
        "my_bookings.html",
        {"bookings": bookings, "server_now": server_now},
    )


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

    now = timezone.now()

    # Отменить можно только бронь, которая сейчас удерживается
    if booking.status != Booking.Status.HELD:
        messages.error(request, "Отменить можно только активную удержанную бронь.")
        return redirect("my_bookings")

    if booking.expires_at <= now:
        booking.status = Booking.Status.EXPIRED
        booking.save(update_fields=["status"])
        messages.error(request, "Срок удержания истёк, бронь уже освобождена.")
        return redirect("my_bookings")

    if booking.session.starts_at <= now:
        messages.error(request, "Отменить бронь можно только до начала сеанса.")
        return redirect("my_bookings")

    booking.status = Booking.Status.CANCELLED
    booking.save()
    messages.success(
        request,
        f"Бронь на место (ряд {booking.seat.row}, место {booking.seat.number}) отменена.",
    )
    return redirect("my_bookings")


def _send_ticket_receipt(ticket):
    booking = ticket.booking
    session = booking.session
    seat = booking.seat
    body = "\n".join(
        [
            f"Здравствуйте, {booking.user.get_username()}!",
            "",
            "Ваш билет оформлен.",
            f"Фильм: {session.movie.title}",
            (
                "Сеанс: "
                f"{timezone.localtime(session.starts_at):%d.%m.%Y %H:%M}"
            ),
            f"Зал: {session.hall.name}",
            f"Место: ряд {seat.row}, место {seat.number}",
            f"Категория места: {seat.get_category_display()}",
            f"Стоимость: {ticket.price} ₽",
            f"Номер билета: {ticket.number}",
            f"Способ оформления: {ticket.get_channel_display()}",
        ]
    )
    return bool(
        send_mail(
            subject=f"Ваш билет {ticket.number}",
            message=body,
            from_email=None,
            recipient_list=[booking.user.email],
            fail_silently=False,
        )
    )


@login_required
def pay_booking(request, pk):
    if request.method != "POST":
        return redirect("my_bookings")

    cashier = is_staff_or_cashier(request.user)
    channel = request.POST.get("channel", Ticket.Channel.ONLINE)
    redirect_name = (
        "cashier_bookings"
        if cashier and channel == Ticket.Channel.CASHBOX
        else "my_bookings"
    )
    if channel not in Ticket.Channel.values:
        messages.error(request, "Выбран недопустимый способ оформления билета.")
        return redirect(redirect_name)
    if channel == Ticket.Channel.CASHBOX and not cashier:
        messages.error(request, "Выкуп через кассу доступен только кассиру или сотруднику.")
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
        if not (is_owner or cashier):
            messages.error(request, "У вас нет прав на выкуп этой брони.")
            return redirect(redirect_name)

        if booking.status == Booking.Status.PAID or hasattr(booking, "ticket"):
            messages.info(request, "Эта бронь уже выкуплена.")
            return redirect(redirect_name)

        if booking.status != Booking.Status.HELD:
            messages.error(request, "Эту бронь нельзя выкупить (она отменена или неактивна).")
            return redirect(redirect_name)

        if booking.expires_at and booking.expires_at <= now:
            booking.status = Booking.Status.EXPIRED
            booking.save()
            messages.error(request, "Время удержания брони истекло, место освободилось.")
            return redirect(redirect_name)

        session_price = SessionPrice.objects.filter(
            session=booking.session,
            category=booking.seat.category,
        ).first()

        if not session_price:
            messages.error(request, "Для этого сеанса и категории места не задана цена.")
            return redirect(redirect_name)

        for _ in range(5):
            ticket_number = f"TKT-{booking.id}-{uuid.uuid4().hex[:6].upper()}"
            try:
                with transaction.atomic():
                    ticket = Ticket.objects.create(
                        booking=booking,
                        number=ticket_number,
                        price=session_price.price,
                        issued_at=now,
                        channel=channel,
                        issued_by=request.user if channel == Ticket.Channel.CASHBOX else None,
                    )
                break
            except IntegrityError:
                ticket_number = None

        if not ticket_number:
            messages.error(request, "Не удалось сформировать уникальный номер билета, попробуйте ещё раз.")
            return redirect(redirect_name)

        booking.status = Booking.Status.PAID
        booking.save()

    email_sent = False
    if booking.user.email:
        try:
            email_sent = _send_ticket_receipt(ticket)
        except (OSError, smtplib.SMTPException):
            logger.exception(
                "Ticket %s was issued but its receipt email could not be sent",
                ticket.number,
            )

    messages.success(
        request,
        f"Билет {ticket_number} успешно оформлен! Стоимость: {session_price.price} ₽.",
    )
    if email_sent:
        messages.info(request, f"Копия билета отправлена на {booking.user.email}.")
    elif booking.user.email:
        messages.warning(
            request,
            "Билет оформлен, но письмо отправить не удалось. "
            "Попробуйте позже или откройте билет в личном кабинете.",
        )
    else:
        messages.warning(
            request,
            "Билет оформлен, но в профиле не указан адрес электронной почты.",
        )
    return redirect(redirect_name)


@login_required
def ticket_detail(request, pk):
    tickets = Ticket.objects.select_related(
        "booking__user",
        "booking__session__movie",
        "booking__session__hall",
        "booking__seat",
        "issued_by",
    )
    cashier = is_staff_or_cashier(request.user)
    if not cashier:
        tickets = tickets.filter(booking__user=request.user)

    ticket = get_object_or_404(tickets, pk=pk)
    return render(
        request,
        "ticket_detail.html",
        {
            "ticket": ticket,
            "back_url_name": "cashier_bookings" if cashier else "my_bookings",
        },
    )


def _sales_csv_response(tickets, start_date, end_date):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="sales_{start_date:%Y-%m-%d}_{end_date:%Y-%m-%d}.csv"'
    )
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(
        [
            "Номер билета",
            "Дата продажи",
            "Фильм",
            "Начало сеанса",
            "Зал",
            "Ряд",
            "Место",
            "Категория места",
            "Покупатель",
            "Цена, руб.",
            "Канал",
            "Кассир",
        ]
    )
    for ticket in tickets.order_by("issued_at", "pk"):
        booking = ticket.booking
        session = booking.session
        seat = booking.seat
        text_values = (
            ticket.number,
            timezone.localtime(ticket.issued_at).strftime("%Y-%m-%d %H:%M:%S"),
            session.movie.title,
            timezone.localtime(session.starts_at).strftime("%Y-%m-%d %H:%M"),
            session.hall.name,
            seat.get_category_display(),
            booking.user.get_username(),
            ticket.get_channel_display(),
            ticket.issued_by.get_username() if ticket.issued_by else "",
        )
        safe_text_values = [
            f"'{value}" if value.startswith(("=", "+", "-", "@", "\t", "\r")) else value
            for value in text_values
        ]
        writer.writerow(
            [
                safe_text_values[0],
                safe_text_values[1],
                safe_text_values[2],
                safe_text_values[3],
                safe_text_values[4],
                seat.row,
                seat.number,
                safe_text_values[5],
                safe_text_values[6],
                ticket.price,
                safe_text_values[7],
                safe_text_values[8],
            ]
        )
    return response


@staff_member_required
def sales_report(request):
    today = timezone.localdate()
    default_start_date = today.replace(day=1)
    form = SalesReportPeriodForm(
        request.GET or None,
        initial={
            "start_date": default_start_date,
            "end_date": today,
        },
    )
    if form.is_bound and not form.is_valid():
        return render(
            request,
            "sales_report.html",
            {
                "form": form,
                "report": None,
            },
        )

    period = form.cleaned_data if form.is_bound else {}
    start_date = period.get("start_date") or default_start_date
    end_date = period.get("end_date") or today
    current_timezone = timezone.get_current_timezone()
    start_datetime = timezone.make_aware(
        datetime.combine(start_date, time.min),
        current_timezone,
    )
    end_datetime = timezone.make_aware(
        datetime.combine(end_date + timedelta(days=1), time.min),
        current_timezone,
    )
    tickets = (
        Ticket.objects.filter(
            issued_at__gte=start_datetime,
            issued_at__lt=end_datetime,
        )
        .select_related(
            "booking__session__movie",
            "booking__session__hall",
            "booking__seat",
            "booking__user",
            "issued_by",
        )
    )
    if request.GET.get("export") == "csv":
        return _sales_csv_response(tickets, start_date, end_date)

    totals = tickets.aggregate(
        ticket_count=Count("pk"),
        revenue=Sum("price"),
        average_ticket_price=Avg("price"),
    )
    booking_period = Booking.objects.filter(
        created_at__gte=start_datetime,
        created_at__lt=end_datetime,
    )
    total_bookings = booking_period.count()
    paid_bookings = booking_period.filter(status=Booking.Status.PAID).count()
    sales_by_movie = list(
        tickets.order_by()
        .values("booking__session__movie__title")
        .annotate(ticket_count=Count("pk"), revenue=Sum("price"))
        .order_by("-ticket_count", "booking__session__movie__title")
    )
    maximum_movie_sales = max(
        (sale["ticket_count"] for sale in sales_by_movie),
        default=0,
    )
    for sale in sales_by_movie:
        sale["movie_title"] = sale.pop("booking__session__movie__title")
        sale["bar_width"] = round(
            sale["ticket_count"] * 100 / maximum_movie_sales
        ) if maximum_movie_sales else 0

    report = {
        "ticket_count": totals["ticket_count"] or 0,
        "revenue": totals["revenue"] or Decimal("0.00"),
        "average_ticket_price": totals["average_ticket_price"] or Decimal("0.00"),
        "paid_bookings": paid_bookings,
        "total_bookings": total_bookings,
        "paid_booking_share": (
            round(paid_bookings * 100 / total_bookings, 1)
            if total_bookings
            else 0
        ),
        "sales_by_movie": sales_by_movie,
    }
    return render(
        request,
        "sales_report.html",
        {
            "form": form,
            "report": report,
            "start_date": start_date,
            "end_date": end_date,
        },
    )


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
    user_review = (
        reviews.filter(user=request.user).first()
        if request.user.is_authenticated
        else None
    )

    # Средняя оценка фильма по всем отзывам (вернёт словарь, например {'avg_rating': 4.5} или None)
    avg_rating = reviews.aggregate(avg_rating=Avg("rating"))["avg_rating"]

    if request.method == "POST":
        if not request.user.is_authenticated:
            messages.error(request, "Чтобы оставить отзыв, войдите в аккаунт.")
            return redirect("login")

        if user_review:
            messages.info(request, "Вы уже оставили отзыв. Его можно изменить ниже.")
            return redirect(f"{reverse('movie_detail', args=[movie.pk])}#reviews")

        form = ReviewForm(request.POST)
        if form.is_valid():
            # Сначала создаём объект отзыва в памяти, чтобы подставить автора и фильм
            review = form.save(commit=False)
            review.user = request.user
            review.movie = movie
            review.save()
            messages.success(request, "Спасибо! Ваш отзыв добавлен.")
            return redirect(f"{reverse('movie_detail', args=[movie.pk])}#reviews")
    else:
        form = ReviewForm()

    return render(
        request,
        "movie_detail.html",
        {
            "movie": movie,
            "upcoming_sessions": upcoming_sessions,
            "reviews": reviews,
            "user_review": user_review,
            "avg_rating": avg_rating,
            "form": form,
        },
    )


@login_required
def review_edit(request, pk):
    review = get_object_or_404(
        Review.objects.select_related("movie"),
        pk=pk,
        user=request.user,
    )
    if request.method == "POST":
        form = ReviewForm(request.POST, instance=review)
        if form.is_valid():
            form.save()
            messages.success(request, "Отзыв обновлён.")
            return redirect(
                f"{reverse('movie_detail', args=[review.movie_id])}#reviews"
            )
    else:
        form = ReviewForm(instance=review)

    return render(
        request,
        "review_form.html",
        {
            "form": form,
            "movie": review.movie,
        },
    )


@login_required
@require_POST
def review_delete(request, pk):
    review = get_object_or_404(Review, pk=pk, user=request.user)
    movie_id = review.movie_id
    review.delete()
    messages.success(request, "Отзыв удалён.")
    return redirect(f"{reverse('movie_detail', args=[movie_id])}#reviews")


@login_required
def cashier_bookings(request):
    if not is_staff_or_cashier(request.user):
        messages.error(request, "Доступ к служебной странице есть только у кассиров и сотрудников.")
        return redirect("index")

    server_now = timezone.now()
    Booking.expire_due(server_now)

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
        search_filter = (
            Q(user__username__icontains=search_query)
            | Q(ticket__number__icontains=search_query)
        )
        if search_query.isdecimal() and len(search_query) <= 18:
            search_filter |= Q(pk=int(search_query))
        bookings = bookings.filter(search_filter)

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
            "server_now": server_now,
        },
    )