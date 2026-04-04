"""
В данном модуле написаны инструменты, которыми пользуется Telegram бот.
"""

from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from vertex import Vertex
from locales.localizer import Localizer
from telebot.types import InlineKeyboardMarkup as K, InlineKeyboardButton as B
import configparser
import datetime
import os.path
import json
import time
import logging
from os.path import exists
from FunPayAPI.common.utils import RegularExpressions
from bs4 import BeautifulSoup as bs
import tg_bot.CBT
from bs4 import BeautifulSoup
from FunPayAPI.account import Account
from FunPayAPI.types import OrderStatuses
import FunPayAPI.types as types
from FunPayAPI.updater.events import *
localizer = Localizer()
_ = localizer.translate
import Utils.vertex_tools
from tg_bot import CBT
import re

logger = logging.getLogger("TGBot")


class NotificationTypes:
    """
    Класс с типами Telegram уведомлений.
    """
    bot_start = "1"
    """Уведомление о старте бота."""
    new_message = "2"
    """Уведомление о новом сообщении."""
    command = "3"
    """Уведомление о введенной команде."""
    new_order = "4"
    """Уведомление о новом заказе."""
    order_confirmed = "5"
    """Уведомление о подтверждении заказа."""
    review = "5r"
    """Уведомление об отзыве."""
    lots_restore = "6"
    """Уведомление о восстановлении лота."""
    lots_deactivate = "7"
    """Уведомление о деактивации лота."""
    delivery = "8"
    """Уведомление о выдаче товара."""
    lots_raise = "9"
    """Уведомление о поднятии лотов."""
    other = "10"
    """Прочие уведомления (плагины)."""
    announcement = "11"
    """Новости / объявления."""
    ad = "12"
    """Реклама."""
    critical = "13"
    """Не отключаемые критически важные уведомления."""


def load_authorized_users() -> list[int]:
    """
    Загружает авторизированных пользователей из кэша.

    :return: список из id авторизированных пользователей.
    """
    return load_json_cache("storage/cache/tg_authorized_users.json", [])


def load_notification_settings() -> dict:
    """
    Загружает настройки Telegram уведомлений из кэша.

    :return: настройки Telegram уведомлений.
    """
    return load_json_cache("storage/cache/notifications.json", {})


def load_answer_templates() -> list[str]:
    """
    Загружает шаблоны ответов из кэша.

    :return: шаблоны ответов из кэша.
    """
    return load_json_cache("storage/cache/answer_templates.json", [])


def load_json_cache(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.loads(f.read())
    except (OSError, json.JSONDecodeError):
        logger.warning(f"Не удалось загрузить JSON-кэш {path}. Использую значение по умолчанию.")
        logger.debug("TRACEBACK", exc_info=True)
        return default


def save_authorized_users(users: list[int]) -> None:
    """
    Сохраняет ID авторизированных пользователей.

    :param users: список id авторизированных пользователей.
    """
    if not os.path.exists("storage/cache/"):
        os.makedirs("storage/cache/")
    with open("storage/cache/tg_authorized_users.json", "w", encoding="utf-8") as f:
        f.write(json.dumps(users))


def save_notification_settings(settings: dict) -> None:
    """
    Сохраняет настройки Telegram-уведомлений.

    :param settings: настройки Telegram-уведомлений.
    """
    if not os.path.exists("storage/cache/"):
        os.makedirs("storage/cache/")
    with open("storage/cache/notifications.json", "w", encoding="utf-8") as f:
        f.write(json.dumps(settings))


def save_answer_templates(templates: list[str]) -> None:
    """
    Сохраняет шаблоны ответов.

    :param templates: список шаблонов.
    """
    if not os.path.exists("storage/cache/"):
        os.makedirs("storage/cache")
    with open("storage/cache/answer_templates.json", "w", encoding="utf-8") as f:
        f.write(json.dumps(templates))


def escape(text: str) -> str:
    """
    Форматирует текст под HTML разметку.

    :param text: текст.
    :return: форматированный текст.
    """
    escape_characters = {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
    }
    for char in escape_characters:
        text = text.replace(char, escape_characters[char])
    return text


def bool_to_text(value: bool | int | str | None, on: str = "🟢", off: str = "🔴"):
    if value is not None and int(value):
        return on
    return off


def get_offset(element_index: int, max_elements_on_page: int) -> int:
    """
    Возвращает смещение списка элементов таким образом, чтобы элемент с индексом element_index оказался в конце списка.

    :param element_index: индекс элемента, который должен оказаться в конце.
    :param max_elements_on_page: максимальное кол-во элементов на 1 странице.
    """
    elements_amount = element_index + 1
    elements_on_page = elements_amount % max_elements_on_page
    elements_on_page = elements_on_page if elements_on_page else max_elements_on_page
    if not elements_amount - elements_on_page:  # если это первая группа команд:
        return 0
    else:
        return element_index - elements_on_page + 1


def add_navigation_buttons(keyboard_obj: K, curr_offset: int,
                           max_elements_on_page: int,
                           elements_on_page: int, elements_amount: int,
                           callback_text: str,
                           extra: list | None = None) -> K:
    """
    Добавляет к переданной клавиатуре кнопки след. / пред. страница.

    :param keyboard_obj: экземпляр клавиатуры.
    :param curr_offset: текущее смещение списка.
    :param max_elements_on_page: максимальное кол-во кнопок на 1 странице.
    :param elements_on_page: текущее кол-во элементов на странице.
    :param elements_amount: общее кол-во элементов.
    :param callback_text: текст callback'а.
    :param extra: доп. данные (будут перечислены через ":")
    """
    extra = (":" + ":".join(str(i) for i in extra)) if extra else ""
    back, forward = True, True

    if curr_offset > 0:
        back_offset = curr_offset - max_elements_on_page if curr_offset > max_elements_on_page else 0
        back_cb = f"{callback_text}:{back_offset}{extra}"
        first_cb = f"{callback_text}:0{extra}"
    else:
        back, back_cb, first_cb = False, CBT.EMPTY, CBT.EMPTY

    if curr_offset + elements_on_page < elements_amount:
        forward_offset = curr_offset + elements_on_page
        last_page_offset = get_offset(elements_amount - 1, max_elements_on_page)
        forward_cb = f"{callback_text}:{forward_offset}{extra}"
        last_cb = f"{callback_text}:{last_page_offset}{extra}"
    else:
        forward, forward_cb, last_cb = False, CBT.EMPTY, CBT.EMPTY

    if back or forward:
        keyboard_obj.row(B("◀️◀️", callback_data=first_cb), B("◀️", callback_data=back_cb),
                         B("▶️", callback_data=forward_cb), B("▶️▶️", callback_data=last_cb))
    return keyboard_obj



def generate_profile_text(vertex: Vertex) -> str:
    """
    Генерирует текст с информацией об аккаунте.

    :return: сгенерированный текст с информацией об аккаунте.
    """
    account = vertex.account
    balance = vertex.balance
    return f"""Статистика аккаунта <b><i>{account.username}</i></b>

<b>ID:</b> <code>{account.id}</code>
<b>Незавершенных заказов:</b> <code>{account.active_sales}</code>
<b>Баланс:</b> 
    <b>₽:</b> <code>{balance.total_rub}₽</code>, доступно для вывода <code>{balance.available_rub}₽</code>.
    <b>$:</b> <code>{balance.total_usd}$</code>, доступно для вывода <code>{balance.available_usd}$</code>.
    <b>€:</b> <code>{balance.total_eur}€</code>, доступно для вывода <code>{balance.available_eur}€</code>.

<i>Обновлено:</i>  <code>{time.strftime('%H:%M:%S', time.localtime(account.last_update))}</code>"""

ORDER_CONFIRMED = {}

def message_hook(vertex: Vertex, event: NewMessageEvent):
    if event.message.type not in [MessageTypes.ORDER_CONFIRMED, MessageTypes.ORDER_CONFIRMED_BY_ADMIN, MessageTypes.ORDER_REOPENED, MessageTypes.REFUND]:
        return
    if event.message.type not in [MessageTypes.ORDER_REOPENED, MessageTypes.REFUND] and bs(event.message.html, "html.parser").find("a").text == vertex.account.username:
        return

    id = RegularExpressions().ORDER_ID.findall(str(event.message))[0][1:]

    if event.message.type in [MessageTypes.ORDER_REOPENED, MessageTypes.REFUND]:
        if id in ORDER_CONFIRMED:
            del ORDER_CONFIRMED[id]
    else:
        ORDER_CONFIRMED[id] = {"time": time.time(), "price": vertex.account.get_order(id).sum}
        with open("storage/cache/advProfileStat.json", "w", encoding="UTF-8") as f:
            f.write(json.dumps(ORDER_CONFIRMED, indent=4, ensure_ascii=False))

def extract_float(text: str) -> float:
    """
    Преобразует строку с ценой в число с плавающей точкой.
    Поддерживает форматы с пробелами/неразрывными пробелами и запятой/точкой как разделителем.
    """
    # Удаляем все, кроме цифр и разделителей, а также пробелы/неразрывные пробелы
    s = re.sub(r"[^\d,\.]", "", text).replace("\u00A0", "").replace(" ", "")
    if not s:
        return 0.0
    # Если присутствуют и точка, и запятая — считаем правый разделитель десятичным, остальные убираем
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            # десятичный разделитель — запятая
            s = s.replace(".", "")
            s = s.replace(",", ".")
        else:
            # десятичный разделитель — точка
            s = s.replace(",", "")
    else:
        # Только запятая — заменяем на точку
        if "," in s:
            s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0

def get_sales(account: Account, start_from: str | None = None, include_paid: bool = True, include_closed: bool = True,
              include_refunded: bool = True, exclude_ids: list[str] | None = None,
              **filters) -> tuple[str | None, list[types.OrderShortcut]]:
    exclude_ids = exclude_ids or []
    link = "https://funpay.com/orders/trade?"

    for name in filters:
        link += f"{name}={filters[name]}&"
    link = link[:-1]

    if start_from:
        filters["continue"] = start_from

    response = account.method("post" if start_from else "get", link, {}, filters, raise_not_200=True)
    html_response = response.content.decode()

    parser = bs(html_response, "html.parser")
    check_user = parser.find("div", {"class": "content-account content-account-login"})

    next_order_id = parser.find("input", {"type": "hidden", "name": "continue"})
    if not next_order_id:
        next_order_id = None
    else:
        next_order_id = next_order_id.get("value")

    order_divs = parser.find_all("a", {"class": "tc-item"})
    if not order_divs:
        return None, []

    sells = []
    for div in order_divs:
        classname = div.get("class")
        if "warning" in classname:
            if not include_refunded:
                continue
            order_status = types.OrderStatuses.REFUNDED
        elif "info" in classname:
            if not include_paid:
                continue
            order_status = types.OrderStatuses.PAID
        else:
            if not include_closed:
                continue
            order_status = types.OrderStatuses.CLOSED

        order_id = div.find("div", {"class": "tc-order"}).text[1:]
        if order_id in exclude_ids:
            continue

        description = div.find("div", {"class": "order-desc"}).find("div").text
        price = float(extract_float(div.find("div", {"class": "tc-price"}).text))

        buyer_div = div.find("div", {"class": "media-user-name"}).find("span")
        buyer_username = buyer_div.text
        buyer_id = int(buyer_div.get("data-href")[:-1].split("https://funpay.com/users/")[1])

        order_obj = types.OrderShortcut(order_id, description, price, buyer_username, buyer_id, order_status,
                                        datetime.datetime.now(), "", str(div))
        sells.append(order_obj)

    return next_order_id, sells

def generate_adv_profile(vertex: Vertex) -> str:
    """
    Генерирует расширенную статистику профиля.
    Защита от ошибок парсинга: при сбое возвращает частичные данные без падения.
    """
    account = vertex.account
    balance = vertex.balance

    # Выбираем валюту и базовое числовое значение из объекта баланса
    # (без сетевых запросов и без перезаписи переменной balance)
    if balance.total_eur:
        currency, balance_value = "€", balance.total_eur
    elif balance.total_usd:
        currency, balance_value = "$", balance.total_usd
    elif balance.total_rub:
        currency, balance_value = "₽", balance.total_rub
    else:
        currency, balance_value = "₽", 0.0
    if exists("storage/cache/advProfileStat.json"):
        global ORDER_CONFIRMED
        ORDER_CONFIRMED = load_json_cache("storage/cache/advProfileStat.json", {})
    sales = {"day": 0, "week": 0, "month": 0, "all": 0}
    salesPrice = {"day": 0.0, "week": 0.0, "month": 0.0, "all": 0.0}
    refunds = {"day": 0, "week": 0, "month": 0, "all": 0}
    refundsPrice = {"day": 0.0, "week": 0.0, "month": 0.0, "all": 0.0}
    canWithdraw = {"now": 0.0, "hour": 0.0, "day": 0.0, "2day": 0.0}

    # Лишний сетевой запрос не выполняем: данные обновляются перед вызовом

    for order in ORDER_CONFIRMED.copy():
        if time.time() - ORDER_CONFIRMED[order]["time"] > 172800:
            del ORDER_CONFIRMED[order]
            continue
        if time.time() - ORDER_CONFIRMED[order]["time"] > 169200:
            canWithdraw["hour"] += ORDER_CONFIRMED[order]["price"]
        elif time.time() - ORDER_CONFIRMED[order]["time"] > 86400:
            canWithdraw["day"] += ORDER_CONFIRMED[order]["price"]
        else:
            canWithdraw["2day"] += ORDER_CONFIRMED[order]["price"]

    # Пытаемся получить актуальный выводимый баланс и валюту из страницы лота.
    # Если верстка поменялась — используем fallback из объекта баланса.
    try:
        randomLotPageLink = bs(account.method("get", "https://funpay.com/lots/693/", {}, {}).text, "html.parser").find("a", {"class": "tc-item"})["href"]
        randomLotPageParse = bs(account.method("get", randomLotPageLink, {}, {}).text, "html.parser")

        parsed_balance_text = randomLotPageParse.select_one(".badge-balance").text.split(" ")
        balance_text_value, balance_text_currency = parsed_balance_text[0], parsed_balance_text[1]

        # Обновляем валюту и отображаемый баланс из страницы, если получилось распарсить
        currency = balance_text_currency
        balance_display = balance_text_value

        selectpicker = randomLotPageParse.find("select", {"class": "form-control input-lg selectpicker"})
        if currency == "₽":
            canWithdraw["now"] = str(selectpicker.get("data-balance-rub", 0) or 0)
        elif currency == "$":
            canWithdraw["now"] = str(selectpicker.get("data-balance-usd", 0) or 0)
        elif currency == "€":
            canWithdraw["now"] = str(selectpicker.get("data-balance-eur", 0) or 0)
        else:
            canWithdraw["now"] = "0"
    except Exception:
        # Fallback: используем доступный баланс по выбранной валюте из объекта баланса
        if currency == "₽":
            canWithdraw["now"] = str(balance.available_rub)
        elif currency == "$":
            canWithdraw["now"] = str(balance.available_usd)
        elif currency == "€":
            canWithdraw["now"] = str(balance.available_eur)
        balance_display = f"{balance_value}"

    # Получаем продажи через встроенный метод API с пагинацией
    try:
        next_order_id, all_sales = account.get_sells()
        while next_order_id is not None:
            time.sleep(1)
            next_order_id, new_sales = account.get_sells(start_from=next_order_id)
            all_sales += new_sales
    except Exception:
        all_sales = []

    # Инициализируем агрегаты по валютам
    currencies = ["USD", "RUB", "EUR"]
    sym = {"USD": "$", "RUB": "₽", "EUR": "€"}
    stats = {
        cur: {
            "sales": {"day": 0, "week": 0, "month": 0, "all": 0},
            "salesPrice": {"day": 0.0, "week": 0.0, "month": 0.0, "all": 0.0},
            "refunds": {"day": 0, "week": 0, "month": 0, "all": 0},
            "refundsPrice": {"day": 0.0, "week": 0.0, "month": 0.0, "all": 0.0},
        }
        for cur in currencies
    }

    now_dt = datetime.datetime.now()
    for sale in all_sales:
        cur = getattr(sale, "currency", None)
        if cur not in stats:
            # неизвестная валюта — пропускаем
            continue
        is_refund = sale.status == OrderStatuses.REFUNDED
        delta = now_dt - sale.date if hasattr(sale, "date") else datetime.timedelta.max

        if is_refund:
            stats[cur]["refunds"]["all"] += 1
            stats[cur]["refundsPrice"]["all"] += sale.price
        else:
            stats[cur]["sales"]["all"] += 1
            stats[cur]["salesPrice"]["all"] += sale.price

        # За сутки / неделю / месяц считаем по относительному времени
        if delta <= datetime.timedelta(days=1):
            if is_refund:
                stats[cur]["refunds"]["day"] += 1
                stats[cur]["refundsPrice"]["day"] += sale.price
            else:
                stats[cur]["sales"]["day"] += 1
                stats[cur]["salesPrice"]["day"] += sale.price
        if delta <= datetime.timedelta(days=7):
            if is_refund:
                stats[cur]["refunds"]["week"] += 1
                stats[cur]["refundsPrice"]["week"] += sale.price
            else:
                stats[cur]["sales"]["week"] += 1
                stats[cur]["salesPrice"]["week"] += sale.price
        if delta <= datetime.timedelta(days=30):
            if is_refund:
                stats[cur]["refunds"]["month"] += 1
                stats[cur]["refundsPrice"]["month"] += sale.price
            else:
                stats[cur]["sales"]["month"] += 1
                stats[cur]["salesPrice"]["month"] += sale.price



    # Формируем блоки статистики по валютам
    sales_blocks = []
    refunds_blocks = []
    for cur in currencies:
        # Показываем только если есть данные по всем времени
        if stats[cur]["sales"]["all"] or stats[cur]["refunds"]["all"]:
            s = stats[cur]["sales"]
            sp = stats[cur]["salesPrice"]
            r = stats[cur]["refunds"]
            rp = stats[cur]["refundsPrice"]
            curr_sym = sym[cur]
            sales_blocks.append(
                f"<b>{curr_sym}</b>\n"
                f"<b>За день:</b> <code>{s['day']} ({sp['day']:.1f} {curr_sym})</code>\n"
                f"<b>За неделю:</b> <code>{s['week']} ({sp['week']:.1f} {curr_sym})</code>\n"
                f"<b>За месяц:</b> <code>{s['month']} ({sp['month']:.1f} {curr_sym})</code>\n"
                f"<b>За всё время:</b> <code>{s['all']} ({sp['all']:.1f} {curr_sym})</code>"
            )
            refunds_blocks.append(
                f"<b>{curr_sym}</b>\n"
                f"<b>За день:</b> <code>{r['day']} ({rp['day']:.1f} {curr_sym})</code>\n"
                f"<b>За неделю:</b> <code>{r['week']} ({rp['week']:.1f} {curr_sym})</code>\n"
                f"<b>За месяц:</b> <code>{r['month']} ({rp['month']:.1f} {curr_sym})</code>\n"
                f"<b>За всё время:</b> <code>{r['all']} ({rp['all']:.1f} {curr_sym})</code>"
            )

    sales_text = "\n\n".join(sales_blocks) if sales_blocks else "<i>Нет данных</i>"
    refunds_text = "\n\n".join(refunds_blocks) if refunds_blocks else "<i>Нет данных</i>"

    return f"""Статистика аккаунта <b><i>{account.username}</i></b>

<b>ID:</b> <code>{account.id}</code>
<b>Баланс:</b> <code>{balance_display} {currency}</code>
<b>Незавершенных заказов:</b> <code>{account.active_sales}</code>

<b>Доступно для вывода</b>
<b>Сейчас:</b> <code>{canWithdraw["now"].split('.')[0]} {currency}</code>
<b>Через час:</b> <code>+{"{:.1f}".format(canWithdraw["hour"])} {currency}</code>
<b>Через день:</b> <code>+{"{:.1f}".format(canWithdraw["day"])} {currency}</code>
<b>Через 2 дня:</b> <code>+{"{:.1f}".format(canWithdraw["2day"])} {currency}</code>

<b>Товаров продано (по валютам)</b>
{sales_text}

<b>Товаров возвращено (по валютам)</b>
{refunds_text}

<i>Обновлено:</i>  <code>{time.strftime('%H:%M:%S', time.localtime(account.last_update))}</code>"""

def get_orders(acc: Account, start_from: str) -> tuple[str | None, list[str]]:
    """
    Получает список ордеров на аккаунте.
    :return: Список с заказами.
    """
    attempts = 3
    while attempts:
        try:
            result = acc.get_sells(start_from=start_from or None, state="paid")
            break
        except:
            attempts -= 1
            time.sleep(1)
    else:
        raise Exception
    orders = result[1]
    old_orders = []
    for i in orders:
        parser = BeautifulSoup(i.html, "html.parser")
        time_text = parser.find("div", {"class": "tc-date-left"}).text
        if any(map(time_text.__contains__, ["сек", "мин", "час", "тол"])):
            continue
        old_orders.append(parser.find("div", {"class": "tc-order"}).text)
    return result[0], old_orders

def get_all_old_orders(acc: Account) -> list[str]:
    """
    Получает список все старых ордеров на аккаунте.
    :param acc: экземпляр аккаунта.
    :return: список старых заказов.
    """
    start_from = ""
    old_orders = []
    while start_from is not None:
        result = get_orders(acc, start_from)
        start_from = result[0]
        old_orders.extend(result[1])
        time.sleep(1)
    return old_orders

def generate_lot_info_text(lot_obj: configparser.SectionProxy) -> str:
    """
    Генерирует текст с информацией о лоте.

    :param lot_obj: секция лота в конфиге автовыдачи.

    :return: сгенерированный текст с информацией о лоте.
    """
    if lot_obj.get("productsFileName") is None:
        file_path = "<b><u>не привязан.</u></b>"
        products_amount = "<code>∞</code>"
    else:
        file_path = f"<code>storage/products/{lot_obj.get('productsFileName')}</code>"
        if not os.path.exists(f"storage/products/{lot_obj.get('productsFileName')}"):
            with open(f"storage/products/{lot_obj.get('productsFileName')}", "w", encoding="utf-8"):
                pass
        products_amount = Utils.vertex_tools.count_products(f"storage/products/{lot_obj.get('productsFileName')}")
        products_amount = f"<code>{products_amount}</code>"

    message = f"""<b>{escape(lot_obj.name)}</b>\n
<b><i>Текст выдачи:</i></b> <code>{escape(lot_obj["response"])}</code>\n
<b><i>Кол-во товаров: </i></b> {products_amount}\n
<b><i>Файл с товарами: </i></b>{file_path}\n
<i>Обновлено:</i>  <code>{datetime.datetime.now().strftime('%H:%M:%S')}</code>"""
    return message
