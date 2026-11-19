"""Генератор демонстрационных данных без зависимости от Django."""
import random
from datetime import datetime, timedelta


GENRES = [
    "Драма", "Комедия", "Триллер", "Фантастика", "Приключения",
    "Мелодрама", "Семейный", "Ужасы",
]

MOVIES = [
    ("Последний рейс", "Пилот региональной авиалинии принимает решение, которое меняет судьбу всех пассажиров.", 118, 2025, 16, ["Драма", "Триллер"]),
    ("Тихий берег", "Семья переезжает в рыбацкую деревню и находит старые письма прежних жильцов.", 104, 2024, 12, ["Драма", "Мелодрама"]),
    ("Сквозь туман", "Группа туристов теряется в горах и вынуждена искать выход вместе.", 97, 2025, 16, ["Триллер", "Приключения"]),
    ("Город огней", "Начинающий журналист расследует загадочные отключения света в мегаполисе.", 126, 2026, 12, ["Фантастика", "Триллер"]),
    ("Рыжий кот и тайна чердака", "Дети находят на чердаке карту и отправляются на поиски клада вместе с котом.", 88, 2025, 0, ["Семейный", "Приключения"]),
    ("Код Феникс", "Команда программистов обнаруживает, что их система начинает принимать решения сама.", 132, 2026, 12, ["Фантастика", "Драма"]),
    ("Мелодия дождя", "Музыкант и художница встречаются каждый вторник в одном и том же кафе.", 101, 2024, 12, ["Мелодрама", "Драма"]),
    ("Звёздный караван", "Экипаж грузового корабля везёт на дальнюю станцию неожиданный груз.", 144, 2026, 12, ["Фантастика", "Приключения"]),
    ("Прощай, лето", "Четверо друзей проводят последние каникулы перед выпускным.", 93, 2025, 12, ["Комедия", "Драма"]),
    ("Охотники за тенью", "Следователь и его напарница берутся за дело, о котором предпочли бы забыть.", 110, 2025, 18, ["Ужасы", "Триллер"]),
    ("Дом на холме", "Новые хозяева старого дома замечают, что по ночам в нём что-то меняется.", 99, 2024, 18, ["Ужасы"]),
    ("Большое приключение Миши", "Маленький медвежонок отправляется в путь, чтобы найти дорогу домой.", 85, 2026, 0, ["Семейный", "Комедия"]),
]

HALLS = [
    ("Зал 1", 8, 12),
    ("Зал 2", 10, 14),
    ("Зал 3", 6, 10),
    ("Зал 4", 8, 10),
]

# Индекс зала, час и минута начала сеанса.
SLOTS = [
    (0, (10, 0)), (0, (14, 0)), (0, (18, 30)), (1, (12, 0)),
    (1, (16, 30)), (2, (20, 0)), (3, (21, 0)),
]

FIRST = [
    "Анна", "Иван", "Мария", "Дмитрий", "Елена", "Сергей", "Ольга",
    "Алексей", "Наталья", "Павел", "Ирина", "Михаил", "Юлия", "Андрей",
    "Татьяна", "Николай", "Светлана", "Артём", "Екатерина",
]
LAST = [
    "Иванов", "Петрова", "Сидоров", "Кузнецова", "Смирнов", "Попова",
    "Васильев", "Соколова", "Михайлов", "Новикова", "Фёдоров",
    "Морозова", "Волков", "Алексеева", "Лебедев", "Семёнова", "Егоров",
    "Павлова", "Козлов",
]

REVIEW_TEXTS = {
    5: ["Очень понравилось, отличная игра актёров и сюжет.", "Лучший фильм этого сезона, рекомендую."],
    4: ["Хороший фильм, местами затянут, но смотрится с интересом.", "Понравилось, особенно финал."],
    3: ["Неплохо, но ожидал большего.", "Средний фильм на один раз."],
    2: ["Сюжет предсказуем, герои не запомнились."],
}


def seat_category(row, rows_count):
    """Два последних ряда зала относятся к категории VIP."""
    return "vip" if row > rows_count - 2 else "standard"


def standard_price(hour):
    if hour < 12:
        return 250
    if hour < 17:
        return 300
    return 400


def build(now):
    """Принимает текущий naive datetime и возвращает набор демоданных."""
    rng = random.Random(5)
    base_day = datetime(now.year, now.month, now.day)
    users = [
        {
            "username": "admin",
            "first_name": "Администратор",
            "last_name": "Кинотеатра",
            "email": "admin@kinozal.local",
            "role": "admin",
        },
        {
            "username": "kassir1",
            "first_name": "Ольга",
            "last_name": "Кассирова",
            "email": "kassir1@kinozal.local",
            "role": "cashier",
        },
        {
            "username": "kassir2",
            "first_name": "Игорь",
            "last_name": "Кассиров",
            "email": "kassir2@kinozal.local",
            "role": "cashier",
        },
    ]
    for i in range(19):
        users.append({
            "username": f"user{i + 1:02d}",
            "first_name": FIRST[i],
            "last_name": LAST[i],
            "email": f"user{i + 1:02d}@example.com",
            "role": "viewer",
        })

    viewers = [user["username"] for user in users if user["role"] == "viewer"]
    cashiers = [user["username"] for user in users if user["role"] == "cashier"]

    sessions = []

    def add_session(day_offset, slot, index):
        hall_idx, (hour, minute) = slot
        starts = base_day + timedelta(days=day_offset, hours=hour, minutes=minute)
        price = standard_price(hour)
        sessions.append({
            "movie_idx": index % len(MOVIES),
            "hall_idx": hall_idx,
            "starts_at": starts,
            "prices": {"standard": price, "vip": price + 150},
        })

    index = 0
    for day_offset in (-3, -2, -1):
        for slot in (SLOTS[1], SLOTS[5]):
            add_session(day_offset, slot, index)
            index += 1
    for day_offset in range(0, 7):
        for slot in SLOTS:
            add_session(day_offset, slot, index)
            index += 1

    hall_seats = [
        [(row, number) for row in range(1, rows + 1) for number in range(1, per_row + 1)]
        for _, rows, per_row in HALLS
    ]
    bookings = []
    ticket_no = 100000

    def add_booking(session_idx, status):
        nonlocal ticket_no
        session = sessions[session_idx]
        seat = used[session_idx].pop()
        username = rng.choice(viewers)
        if status == "held":
            expires = now + timedelta(minutes=rng.randint(3, 14))
            created = expires - timedelta(minutes=15)
        elif status == "expired":
            created = now - timedelta(hours=rng.randint(2, 20))
            expires = created + timedelta(minutes=15)
        else:
            created = session["starts_at"] - timedelta(
                hours=rng.randint(1, 30),
                minutes=rng.randint(0, 59),
            )
            if created > now:
                created = now - timedelta(minutes=rng.randint(30, 600))
            expires = created + timedelta(minutes=15)

        booking = {
            "username": username,
            "session_idx": session_idx,
            "hall_idx": session["hall_idx"],
            "row": seat[0],
            "number": seat[1],
            "status": status,
            "created_at": created,
            "expires_at": expires,
            "ticket": None,
        }
        if status == "paid":
            ticket_no += 1
            rows_count = HALLS[session["hall_idx"]][1]
            category = seat_category(seat[0], rows_count)
            cashbox = rng.random() < 0.3
            issued = min(
                created + timedelta(minutes=rng.randint(1, 12)),
                expires - timedelta(minutes=1),
            )
            booking["ticket"] = {
                "number": f"T-{ticket_no}",
                "price": session["prices"][category],
                "channel": "cashbox" if cashbox else "online",
                "issued_by": rng.choice(cashiers) if cashbox else None,
                "issued_at": issued,
            }
        bookings.append(booking)

    used = {}
    for index, session in enumerate(sessions):
        pool = hall_seats[session["hall_idx"]][:]
        rng.shuffle(pool)
        used[index] = pool

    past_count = 6
    for index in range(past_count):
        for _ in range(rng.randint(6, 9)):
            add_booking(index, "paid")
        add_booking(index, "cancelled")
    for index in range(past_count, past_count + 16):
        for _ in range(rng.randint(3, 6)):
            choice = rng.random()
            status = (
                "paid" if choice < 0.68
                else "held" if choice < 0.83
                else "cancelled" if choice < 0.94
                else "expired"
            )
            add_booking(index, status)

    pairs = []
    for booking in bookings:
        if booking["status"] == "paid":
            movie_idx = sessions[booking["session_idx"]]["movie_idx"]
            pair = (booking["username"], movie_idx)
            if pair not in pairs:
                pairs.append(pair)

    rng.shuffle(pairs)
    reviews = []
    for username, movie_idx in pairs[:16]:
        rating = rng.choice([5, 5, 4, 4, 4, 3, 3, 2])
        reviews.append({
            "username": username,
            "movie_idx": movie_idx,
            "rating": rating,
            "text": rng.choice(REVIEW_TEXTS[rating]),
            "created_at": now - timedelta(
                days=rng.randint(0, 3),
                hours=rng.randint(0, 12),
            ),
        })

    return {
        "genres": GENRES,
        "movies": MOVIES,
        "halls": HALLS,
        "users": users,
        "sessions": sessions,
        "bookings": bookings,
        "reviews": reviews,
    }
