from django.contrib.auth.decorators import user_passes_test


def is_staff_or_cashier(user):
    # Пускаем только вошедших пользователей: кассиров, сотрудников и суперпользователей
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    # Проверяем, состоит ли пользователь в группе с названием «Кассир» (в двух вариантах написания)
    return user.groups.filter(name__in=["Кассир", "cashier"]).exists()


def can_manage_booking(user, booking):
    # Обычному пользователю можно работать только со своей бронью, кассиру/админу — с любой
    if not user or not user.is_authenticated:
        return False
    if is_staff_or_cashier(user):
        return True
    return booking.user_id == user.id


staff_or_cashier_required = user_passes_test(is_staff_or_cashier)