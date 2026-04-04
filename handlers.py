"""
В данном модуле написаны хэндлеры для разных эвентов.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from vertex import Vertex

from FunPayAPI.types import OrderShortcut, Order
from FunPayAPI import exceptions, utils as fp_utils
from FunPayAPI.updater.events import *


from tg_bot import utils, keyboards
from Utils import vertex_tools
from locales.localizer import Localizer
from threading import Thread
import configparser
from datetime import datetime
import logging
import time
import re



LAST_STACK_ID = ""
MSG_LOG_LAST_STACK_ID = ""


logger = logging.getLogger("FPV.handlers")
localizer = Localizer()
_ = localizer.translate


ORDER_HTML_TEMPLATE = """<a href="https://funpay.com/orders/DELITEST/" class="tc-item">
   <div class="tc-date" bis_skin_checked="1">
      <div class="tc-date-time" bis_skin_checked="1">сегодня, $date</div>
      <div class="tc-date-left" bis_skin_checked="1">только что</div>
   </div>
   <div class="tc-order" bis_skin_checked="1">#DELITEST</div>
   <div class="order-desc" bis_skin_checked="1">
      <div bis_skin_checked="1">$lot_name</div>
      <div class="text-muted" bis_skin_checked="1">Автовыдача, Тест</div>
   </div>
   <div class="tc-user" bis_skin_checked="1">
      <div class="media media-user offline" bis_skin_checked="1">
         <div class="media-left" bis_skin_checked="1">
            <div class="avatar-photo pseudo-a" tabindex="0" data-href="https://funpay.com/users/000000/" style="background-image: url(/img/layout/avatar.png);" bis_skin_checked="1"></div>
         </div>
         <div class="media-body" bis_skin_checked="1">
            <div class="media-user-name" bis_skin_checked="1">
               <span class="pseudo-a" tabindex="0" data-href="https://funpay.com/users/000000/">$username</span>
            </div>
            <div class="media-user-status" bis_skin_checked="1">был 1.000.000 лет назад</div>
         </div>
      </div>
   </div>
   <div class="tc-status text-primary" bis_skin_checked="1">Оплачен</div>
   <div class="tc-price text-nowrap tc-seller-sum" bis_skin_checked="1">999999.0 <span class="unit">₽</span></div>
</a>"""


AMOUNT_EXPRESSION = re.compile(r'\d+ шт\.')


# INIT MESSAGE
def save_init_chats_handler(c: Vertex, e: InitialChatEvent):
    """
    Кэширует существующие чаты (чтобы не отправлять приветственные сообщения).
    """
    if c.MAIN_CFG["Greetings"].getboolean("cacheInitChats") and e.chat.id not in c.old_users:
        c.old_users.append(e.chat.id)
        vertex_tools.cache_old_users(c.old_users)


# NEW MESSAGE / LAST CHAT MESSAGE CHANGED
def old_log_msg_handler(c: Vertex, e: LastChatMessageChangedEvent):
    """
    Логирует полученное сообщение.
    """
    if not c.old_mode_enabled:
        return
    text, chat_name, chat_id = str(e.chat), e.chat.name, e.chat.id
    username = c.account.username if not e.chat.unread else e.chat.name

    logger.info(_("log_new_msg", chat_name, chat_id))
    for index, line in enumerate(text.split("\n")):
        if not index:
            logger.info(f"$MAGENTA└───> $YELLOW{username}: $CYAN{line}")
        else:
            logger.info(f"      $CYAN{line}")


def log_msg_handler(c: Vertex, e: NewMessageEvent):
    global MSG_LOG_LAST_STACK_ID
    if e.stack.id() == MSG_LOG_LAST_STACK_ID:
        return

    chat_name, chat_id = e.message.chat_name, e.message.chat_id

    logger.info(_("log_new_msg", chat_name, chat_id))
    for index, event in enumerate(e.stack.get_stack()):
        username, text = event.message.author, event.message.text or event.message.image_link
        for line_index, line in enumerate(text.split("\n")):
            if not index and not line_index:
                logger.info(f"$MAGENTA└───> $YELLOW{username}: $CYAN{line}")
            elif not line_index:
                logger.info(f"      $YELLOW{username}: $CYAN{line}")
            else:
                logger.info(f"      $CYAN{line}")
    MSG_LOG_LAST_STACK_ID = e.stack.id()


def greetings_handler(c: Vertex, e: NewMessageEvent | LastChatMessageChangedEvent):
    """
    Отправляет приветственное сообщение.
    """
    if not c.MAIN_CFG["Greetings"].getboolean("sendGreetings"):
        return
    if not c.old_mode_enabled:
        if isinstance(e, LastChatMessageChangedEvent):
            return
        obj = e.message
        chat_id, chat_name, mtype, its_me = obj.chat_id, obj.chat_name, obj.type, obj.author_id == c.account.id
    else:
        obj = e.chat
        chat_id, chat_name, mtype, its_me = obj.id, obj.name, obj.last_message_type, not obj.unread

    if any([chat_id in c.old_users, its_me,
            (mtype is not MessageTypes.NON_SYSTEM and c.MAIN_CFG["Greetings"].getboolean("ignoreSystemMessages"))]):
        return

    logger.info(_("log_sending_greetings", chat_name, chat_id))
    text = vertex_tools.format_msg_text(c.MAIN_CFG["Greetings"]["greetingsText"], obj)
    Thread(target=c.send_message, args=(chat_id, text, chat_name), daemon=True).start()


def add_old_user_handler(c: Vertex, e: NewMessageEvent | LastChatMessageChangedEvent):
    """
    Добавляет пользователя в список написавших.
    """
    if not c.old_mode_enabled:
        if isinstance(e, LastChatMessageChangedEvent):
            return
        chat_id = e.message.chat_id
    else:
        chat_id = e.chat.id

    if chat_id in c.old_users:
        return
    c.old_users.append(chat_id)
    vertex_tools.cache_old_users(c.old_users)


def send_response_handler(c: Vertex, e: NewMessageEvent | LastChatMessageChangedEvent):
    """
    Проверяет, является ли сообщение командой, и если да, отправляет ответ на данную команду.
    """
    if not c.autoresponse_enabled:
        return
    if not c.old_mode_enabled:
        if isinstance(e, LastChatMessageChangedEvent):
            return
        obj, mtext = e.message, str(e.message)
        chat_id, chat_name, username = e.message.chat_id, e.message.chat_name, e.message.author
    else:
        obj, mtext = e.chat, str(e.chat)
        chat_id, chat_name, username = obj.id, obj.name, obj.name

    if any([c.bl_response_enabled and username in c.blacklist, (command := mtext.strip().lower()) not in c.AR_CFG]):
        return

    logger.info(_("log_new_cmd", command, chat_name, chat_id))
    response_text = vertex_tools.format_msg_text(c.AR_CFG[command]["response"], obj)
    Thread(target=c.send_message, args=(chat_id, response_text, chat_name), daemon=True).start()


def old_send_new_msg_notification_handler(c: Vertex, e: LastChatMessageChangedEvent):
    if any([not c.old_mode_enabled, not c.telegram, not e.chat.unread, c.bl_msg_notification_enabled and e.chat.name in c.blacklist,
            e.chat.last_message_type is not MessageTypes.NON_SYSTEM, str(e.chat).strip().lower() in c.AR_CFG.sections(),
            str(e.chat).startswith("!автовыдача")]):
        return

    text = f"<i><b>👤 {e.chat.name}: </b></i><code>{str(e.chat)}</code>"
    kb = keyboards.reply(e.chat.id, e.chat.name, extend=True)
    Thread(target=c.telegram.send_notification, args=(text, kb, utils.NotificationTypes.new_message),
           daemon=True).start()


def send_new_msg_notification_handler(c: Vertex, e: NewMessageEvent) -> None:
    """
    Отправляет уведомление о новом сообщении в телеграм.
    """
    global LAST_STACK_ID
    if not c.telegram or e.stack.id() == LAST_STACK_ID:
        return
    LAST_STACK_ID = e.stack.id()

    chat_id, chat_name = e.message.chat_id, e.message.chat_name
    if c.bl_msg_notification_enabled and chat_name in c.blacklist:
        return

    events = []
    nm, m, f, b = False, False, False, False
    for i in e.stack.get_stack():
        if i.message.author_id == 0:
            if c.include_fp_msg_enabled:
                events.append(i)
                f = True
        elif i.message.by_bot:
            if c.include_bot_msg_enabled:
                events.append(i)
                b = True
        elif i.message.author_id == c.account.id:
            if c.include_my_msg_enabled:
                events.append(i)
                m = True
        else:
            events.append(i)
            nm = True
    if not events:
        return

    if [m, f, b, nm].count(True) == 1 and \
            any([m and not c.only_my_msg_enabled, f and not c.only_fp_msg_enabled, b and not c.only_bot_msg_enabled]):
        return

    text = ""
    last_message_author_id = -1
    last_by_bot = False
    for i in events:
        message_text = str(e.message)
        if message_text.strip().lower() in c.AR_CFG.sections() and len(events) < 2:
            continue
        elif message_text.startswith("!автовыдача") and len(events) < 2:
            continue

        if i.message.author_id == last_message_author_id and i.message.by_bot == last_by_bot:
            author = ""
        elif i.message.author_id == c.account.id:
            author = f"<i><b>🤖 {_('you')} (<i>FPV</i>):</b></i> " if i.message.by_bot else f"<i><b>🫵 {_('you')}:</b></i> "
        elif i.message.author_id == 0:
            author = f"<i><b>🔵 {i.message.author}: </b></i>"
        elif i.message.badge:
            author = f"<i><b>🆘 {i.message.author} ({_('support')}): </b></i>"
        elif i.message.author == i.message.chat_name:
            author = f"<i><b>👤 {i.message.author}: </b></i>"
        else:
            author = f"<i><b>🆘 {i.message.author} {_('support')}: </b></i>"
        msg_text = f"<code>{i.message}</code>" if i.message.text else f"<a href=\"{i.message}\">{_('photo')}</a>"
        text += f"{author}{msg_text}\n\n"
        last_message_author_id = i.message.author_id
        last_by_bot = i.message.by_bot

    kb = keyboards.reply(chat_id, chat_name, extend=True)
    Thread(target=c.telegram.send_notification, args=(text, kb, utils.NotificationTypes.new_message),
           daemon=True).start()


def send_review_notification(c: Vertex, order: Order, chat_id: int, reply_text: str | None):
    if not c.telegram:
        return
    reply_text = f"\n\n🗨️<b>Ответ:</b> \n<code>{utils.escape(reply_text)}</code>" if reply_text else ""
    Thread(target=c.telegram.send_notification,
           args=(f"🔮 Вы получили {'⭐' * order.review.stars} за заказ <code>{order.id}</code>!\n\n"
                 f"💬<b>Отзыв:</b>\n<code>{utils.escape(order.review.text)}</code>{reply_text}",
                 keyboards.new_order(order.id, order.buyer_username, chat_id),
                 utils.NotificationTypes.review),
           daemon=True).start()


def process_review_handler(c: Vertex, e: NewMessageEvent | LastChatMessageChangedEvent):
    if not c.old_mode_enabled:
        if isinstance(e, LastChatMessageChangedEvent):
            return
        message_type, its_me = e.message.type, c.account.username in str(e.message)
        message_text, chat_id = str(e.message), e.message.chat_id
    else:
        message_type, its_me = e.chat.last_message_type, c.account.username in str(e.chat)
        message_text, chat_id = str(e.chat), e.chat.id

    if message_type not in [types.MessageTypes.NEW_FEEDBACK, types.MessageTypes.FEEDBACK_CHANGED] or its_me:
        return

    def send_reply():
        res = fp_utils.RegularExpressions()
        order_id = res.ORDER_ID.findall(message_text)
        if not order_id:
            return
        order_id = order_id[0][1:]
        try:
            order = c.account.get_order(order_id)
        except:
            logger.error(f"Не удалось получить информацию о заказе #{order_id}.")
            logger.debug("TRACEBACK", exc_info=True)
            return

        if not order.review or not order.review.stars:
            return

        logger.info(f"Изменен отзыв на заказ #{order.id}.")

        toggle = f"star{order.review.stars}Reply"
        text = f"star{order.review.stars}ReplyText"
        reply_text = None
        if c.MAIN_CFG["ReviewReply"].getboolean(toggle) and c.MAIN_CFG["ReviewReply"].get(text):
            try:
                reply_text = vertex_tools.format_order_text(c.MAIN_CFG["ReviewReply"].get(text), order)
                c.account.send_review(order_id, reply_text)
            except:
                logger.error(f"Произошла ошибка при ответе на отзыв {order_id}.")
                logger.debug("TRACEBACK", exc_info=True)
        send_review_notification(c, order, chat_id, reply_text)
    Thread(target=send_reply, daemon=True).start()


def send_command_notification_handler(c: Vertex, e: NewMessageEvent | LastChatMessageChangedEvent):
    """
    Отправляет уведомление о введенной команде в телеграм.
    """
    if not c.telegram:
        return
    if not c.old_mode_enabled:
        if isinstance(e, LastChatMessageChangedEvent):
            return
        obj, message_text = e.message, str(e.message)
        chat_id, chat_name, username = e.message.chat_id, e.message.chat_name, e.message.author
    else:
        obj, message_text = e.chat, str(e.chat)
        chat_id, chat_name, username = obj.id, obj.name, obj.name if obj.unread else c.account.username

    if c.bl_cmd_notification_enabled and username in c.blacklist:
        return
    command = message_text.strip().lower()
    if command not in c.AR_CFG or not c.AR_CFG[command].getboolean("telegramNotification"):
        return

    if not c.AR_CFG[command].get("notificationText"):
        text = f"🧑‍💻 Пользователь <b><i>{username}</i></b> ввел команду <code>{utils.escape(command)}</code>."
    else:
        text = vertex_tools.format_msg_text(c.AR_CFG[command]["notificationText"], obj)

    Thread(target=c.telegram.send_notification, args=(text, keyboards.reply(chat_id, chat_name),
                                                      utils.NotificationTypes.command), daemon=True).start()


def test_auto_delivery_handler(c: Vertex, e: NewMessageEvent | LastChatMessageChangedEvent):
    """
    Выполняет тест автовыдачи.
    """
    if not c.old_mode_enabled:
        if isinstance(e, LastChatMessageChangedEvent):
            return
        obj, message_text, chat_name = e.message, str(e.message), e.message.chat_name
    else:
        obj, message_text, chat_name = e.chat, str(e.chat), e.chat.name

    if not message_text.startswith("!автовыдача"):
        return

    split = message_text.split()
    if len(split) < 2:
        logger.warning("Одноразовый ключ автовыдачи не обнаружен.")
        return

    key = split[1].strip()
    if key not in c.delivery_tests:
        logger.warning("Невалидный одноразовый ключ автовыдачи.")
        return

    lot_name = c.delivery_tests[key]
    del c.delivery_tests[key]
    date = datetime.now()
    date_text = date.strftime("%H:%M")
    html = ORDER_HTML_TEMPLATE.replace("$username", chat_name).replace("$lot_name", lot_name).replace("$date", date_text)

    fake_order = OrderShortcut("ADTEST", lot_name, 0.0, chat_name, 000000, types.OrderStatuses.PAID,
                               date, "Авто-выдача, Тест", html)

    fake_event = NewOrderEvent(e.runner_tag, fake_order)
    c.run_handlers(c.new_order_handlers, (c, fake_event,))


def send_categories_raised_notification_handler(c: Vertex, cat: types.Category) -> None:
    """
    Отправляет уведомление о поднятии лотов в Telegram.
    """
    if not c.telegram:
        return

    text = f"""⤴️<b><i>Поднял все лоты категории</i></b> <code>{cat.name}</code>"""
    Thread(target=c.telegram.send_notification,
           args=(text, ),
           kwargs={"notification_type": utils.NotificationTypes.lots_raise}, daemon=True).start()


# Изменен список ордеров (REGISTER_TO_ORDERS_LIST_CHANGED)
def get_lot_config_by_name(c: Vertex, name: str) -> configparser.SectionProxy | None:
    """
    Ищет секцию лота в конфиге автовыдачи.

    :param c: объект вертекса.
    :param name: название лота.

    :return: секцию конфига или None.
    """
    matched_section_name = None
    lot_name = name.casefold()
    for section_name in c.AD_CFG.sections():
        if section_name.casefold() not in lot_name:
            continue
        if matched_section_name is None or len(section_name) > len(matched_section_name):
            matched_section_name = section_name
    return c.AD_CFG[matched_section_name] if matched_section_name else None


def check_products_amount(config_obj: configparser.SectionProxy) -> int:
    file_name = config_obj.get("productsFileName")
    if not file_name:
        return 1
    return vertex_tools.count_products(f"storage/products/{file_name}")


def is_auto_delivery_disabled(config_obj: configparser.SectionProxy) -> bool:
    return config_obj.get("disable") == "1" or config_obj.get("disableAutoDelivery") == "1"


def update_current_lots_handler(c: Vertex, e: OrdersListChangedEvent):
    logger.info("Получаю информацию о лотах...")
    attempts = 3
    while attempts:
        try:
            c.curr_profile = c.account.get_user(c.account.id)
            c.curr_profile_last_tag = e.runner_tag
            break
        except:
            logger.error("Произошла ошибка при получении информации о лотах.")
            logger.debug("TRACEBACK", exc_info=True)
            attempts -= 1
            time.sleep(2)
    else:
        logger.error("Не удалось получить информацию о лотах: превышено кол-во попыток.")
        return


# Новый ордер (REGISTER_TO_NEW_ORDER)
def log_new_order_handler(c: Vertex, e: NewOrderEvent, *args):
    """
    Логирует новый заказ.
    """
    logger.info(f"Новый заказ! ID: $YELLOW#{e.order.id}$RESET")


def setup_event_attributes_handler(c: Vertex, e: NewOrderEvent, *args):
    config_section_obj = get_lot_config_by_name(c, e.order.description)
    config_section_name = config_section_obj.name if config_section_obj else None

    attributes = {"config_section_name": config_section_name, "config_section_obj": config_section_obj,
                  "delivered": False, "delivery_text": None, "goods_delivered": 0, "goods_left": None,
                  "error": 0, "error_text": None}
    for i in attributes:
        setattr(e, i, attributes[i])

    if config_section_obj is None:
        logger.info("Лот не найден в конфиге авто-выдачи!")  # todo
    else:
        logger.info("Лот найден в конфиге авто-выдачи!")  # todo


def send_new_order_notification_handler(c: Vertex, e: NewOrderEvent, *args):
    """
    Отправляет уведомления о новом заказе в телеграм.
    """
    if not c.telegram:
        return
    if e.order.buyer_username in c.blacklist and c.MAIN_CFG["BlockList"].getboolean("blockNewOrderNotification"):
        return
    if not (config_obj := getattr(e, "config_section_obj")):
        delivery_info = _("ntfc_new_order_not_in_cfg")
    else:
        if not c.autodelivery_enabled:
            delivery_info = _("ntfc_new_order_ad_disabled")
        elif is_auto_delivery_disabled(config_obj):
            delivery_info = _("ntfc_new_order_ad_disabled_for_lot")
        elif c.bl_delivery_enabled and e.order.buyer_username in c.blacklist:
            delivery_info = _("ntfc_new_order_user_blocked")
        else:
            delivery_info = _("ntfc_new_order_will_be_delivered")
    text = _("ntfc_new_order", utils.escape(e.order.description), e.order.buyer_username, e.order.price, e.order.id,
             delivery_info)

    chat_id = c.account.get_chat_by_name(e.order.buyer_username, True).id
    keyboard = keyboards.new_order(e.order.id, e.order.buyer_username, chat_id)
    Thread(target=c.telegram.send_notification, args=(text, keyboard, utils.NotificationTypes.new_order),
           daemon=True).start()


def deliver_goods(c: Vertex, e: NewOrderEvent, *args):
    chat_id = c.account.get_chat_by_name(e.order.buyer_username).id
    cfg_obj = getattr(e, "config_section_obj")
    delivery_text = vertex_tools.format_order_text(cfg_obj["response"], e.order)

    amount, goods_left, products = 1, -1, []
    try:
        if file_name := cfg_obj.get("productsFileName"):
            if c.multidelivery_enabled and not cfg_obj.getboolean("disableMultiDelivery"):
                amount_re = AMOUNT_EXPRESSION.findall(e.order.description)
                amount = int(amount_re[0].split(" ")[0]) if amount_re else 1
            products, goods_left = vertex_tools.get_products(f"storage/products/{file_name}", amount)
            delivery_text = delivery_text.replace("$product", "\n".join(products).replace("\\n", "\n"))
    except Exception as exc:
        logger.error(f"Произошла ошибка при получении товаров для заказа $YELLOW{e.order.id}: {str(exc)}$RESET")
        logger.debug("TRACEBACK", exc)
        setattr(e, "error", 1)
        setattr(e, "error_text", f"Произошла ошибка при получении товаров для заказа {e.order.id}: {str(exc)}")
        return

    result = c.send_message(chat_id, delivery_text, e.order.buyer_username)
    if not result:
        logger.error(f"Не удалось отправить товар для ордера $YELLOW{e.order.id}$RESET.")
        setattr(e, "error", 1)
        setattr(e, "error_text", f"Не удалось отправить сообщение с товаром для заказа {e.order.id}.")
        if file_name and products:
            vertex_tools.add_products(f"storage/products/{file_name}", products, at_zero_position=True)
    else:
        logger.info(f"Товар для заказа {e.order.id} выдан.")
        setattr(e, "delivered", True)
        setattr(e, "delivery_text", delivery_text)
        setattr(e, "goods_delivered", amount)
        setattr(e, "goods_left", goods_left)


def deliver_product_handler(c: Vertex, e: NewOrderEvent, *args) -> None:
    """
    Обертка для deliver_product(), обрабатывающая ошибки.
    """
    if not c.MAIN_CFG["FunPay"].getboolean("autoDelivery"):
        return
    if e.order.buyer_username in c.blacklist and c.MAIN_CFG["BlockList"].getboolean("blockDelivery"):
        logger.info(f"Пользователь {e.order.buyer_username} находится в ЧС и включена блокировка автовыдачи. "
                    f"$YELLOW(ID: {e.order.id})$RESET")
        return

    if (config_section_obj := getattr(e, "config_section_obj")) is None:
        return
    if is_auto_delivery_disabled(config_section_obj):
        logger.info(f"Для лота \"{e.order.description}\" отключена автовыдача.")
        return

    c.run_handlers(c.pre_delivery_handlers, (c, e))
    deliver_goods(c, e, *args)
    c.run_handlers(c.post_delivery_handlers, (c, e))


# REGISTER_TO_POST_DELIVERY
def send_delivery_notification_handler(c: Vertex, e: NewOrderEvent):
    """
    Отправляет уведомление в телеграм об отправке товара.
    """
    if c.telegram is None:
        return

    if getattr(e, "error"):
        text = f"""❌ <code>{getattr(e, "error_text")}</code>"""
    else:
        amount = "<b>∞</b>" if getattr(e, "goods_left") == -1 else f"<code>{getattr(e, 'goods_left')}</code>"
        text = f"""✅ Успешно выдал товар для ордера <code>{e.order.id}</code>.\n
🛒 <b><i>Товар:</i></b>
<code>{utils.escape(getattr(e, "delivery_text"))}</code>\n
📋 <b><i>Осталось товаров: </i></b>{amount}"""

    Thread(target=c.telegram.send_notification, args=(text,),
           kwargs={"notification_type": utils.NotificationTypes.delivery}, daemon=True).start()


def update_lot_state(vertex: Vertex, lot: types.LotShortcut, task: int) -> bool:
    """
    Обновляет состояние лота

    :param vertex: объект вертекса.
    :param lot: объект лота.
    :param task: -1 - деактивировать лот. 1 - активировать лот.

    :return: результат выполнения.
    """
    attempts = 3
    while attempts:
        try:
            lot_fields = vertex.account.get_lot_fields(lot.id)
            if task == 1:
                lot_fields.active = True
                vertex.account.save_lot(lot_fields)
                logger.info(f"Восстановил лот $YELLOW{lot.description}$RESET.")
            elif task == -1:
                lot_fields.active = False
                vertex.account.save_lot(lot_fields)
                logger.info(f"Деактивировал лот $YELLOW{lot.description}$RESET.")
            return True
        except Exception as e:
            if isinstance(e, exceptions.RequestFailedError) and e.status_code == 404:
                logger.error(f"Произошла ошибка при изменении состояния лота $YELLOW{lot.description}$RESET:"
                             "лот не найден.")
                return False
            logger.error(f"Произошла ошибка при изменении состояния лота $YELLOW{lot.description}$RESET.")
            logger.debug("TRACEBACK", exc_info=True)
            attempts -= 1
            time.sleep(2)
    logger.error(f"Не удалось изменить состояние лота $YELLOW{lot.description}$RESET: превышено кол-во попыток.")
    return False


def update_lots_states(vertex: Vertex, event: NewOrderEvent):
    if not any([vertex.autorestore_enabled, vertex.autodisable_enabled]):
        return
    if vertex.curr_profile_last_tag != event.runner_tag or vertex.last_state_change_tag == event.runner_tag:
        return

    lots = vertex.curr_profile.get_sorted_lots(1)

    deactivated = []
    restored = []
    for lot in vertex.profile.get_lots():
        # -1 - деактивировать
        # 0 - ничего не делать
        # 1 - восстановить
        current_task = 0
        config_obj = get_lot_config_by_name(vertex, lot.description)

        # Если лот уже деактивирован
        if lot.id not in lots:
            # и не найден в конфиге автовыдачи (глобальное автовосстановление включено)
            if config_obj is None:
                if vertex.autorestore_enabled:
                    current_task = 1

            # и найден в конфиге автовыдачи
            else:
                # и глобальное автовосстановление вкл. + не выключено в самом лоте в конфиге автовыдачи
                if vertex.autorestore_enabled and config_obj.get("disableAutoRestore") in ["0", None]:
                    # если глобальная автодеактивация выключена - восстанавливаем.
                    if not vertex.autodisable_enabled:
                        current_task = 1
                    # если глобальная автодеактивация включена - восстанавливаем только если есть товары.
                    else:
                        if check_products_amount(config_obj):
                            current_task = 1

        # Если же лот активен
        else:
            # и найден в конфиге автовыдачи
            if config_obj:
                products_count = check_products_amount(config_obj)
                # и все условия выполнены: нет товаров + включено глобальная автодеактивация + она не выключена в
                # самом лоте в конфига автовыдачи - отключаем.
                if all((not products_count, vertex.MAIN_CFG["FunPay"].getboolean("autoDisable"),
                        config_obj.get("disableAutoDisable") in ["0", None])):
                    current_task = -1

        if current_task:
            result = update_lot_state(vertex, lot, current_task)
            if result:
                if current_task == -1:
                    deactivated.append(lot.description)
                elif current_task == 1:
                    restored.append(lot.description)
            time.sleep(0.5)

    if deactivated:
        lots = "\n".join(deactivated)
        text = f"""🔴 <b>Деактивировал лоты:</b>
        
<code>{lots}</code>"""
        Thread(target=vertex.telegram.send_notification, args=(text, ),
               kwargs={"notification_type": utils.NotificationTypes.lots_deactivate}, daemon=True).start()
    if restored:
        lots = "\n".join(restored)
        text = f"""🟢 <b>Активировал лоты:</b>

<code>{lots}</code>"""
        Thread(target=vertex.telegram.send_notification, args=(text,),
               kwargs={"notification_type": utils.NotificationTypes.lots_restore}, daemon=True).start()
    vertex.last_state_change_tag = event.runner_tag


def update_lots_state_handler(vertex: Vertex, event: NewOrderEvent, *args):
    Thread(target=update_lots_states, args=(vertex, event), daemon=True).start()


# BIND_TO_ORDER_STATUS_CHANGED
def send_thank_u_message_handler(c: Vertex, e: OrderStatusChangedEvent):
    """
    Отправляет ответное сообщение на подтверждение заказа.
    """
    if not c.MAIN_CFG["OrderConfirm"].getboolean("sendReply") or e.order.status is not types.OrderStatuses.CLOSED:
        return

    text = vertex_tools.format_order_text(c.MAIN_CFG["OrderConfirm"]["replyText"], e.order)
    chat = c.account.get_chat_by_name(e.order.buyer_username, True)
    logger.info(f"Пользователь $YELLOW{e.order.buyer_username}$RESET подтвердил выполнение заказа "
                f"$YELLOW{e.order.id}.$RESET")
    logger.info(f"Отправляю ответное сообщение ...")
    Thread(target=c.send_message, args=(chat.id, text, e.order.buyer_username), daemon=True).start()


def send_order_confirmed_notification_handler(vertex: Vertex, event: OrderStatusChangedEvent):
    """
    Отправляет уведомление о подтверждении заказа в Telegram.
    """
    if not event.order.status == types.OrderStatuses.CLOSED:
        return

    chat = vertex.account.get_chat_by_name(event.order.buyer_username, True)
    Thread(target=vertex.telegram.send_notification,
           args=(f"""🪙 Пользователь <a href="https://funpay.com/chat/?node={chat.id}">{event.order.buyer_username}</a> """
                 f"""подтвердил выполнение заказа <code>{event.order.id}</code>.""",
                 keyboards.new_order(event.order.id, event.order.buyer_username, chat.id),
                 utils.NotificationTypes.order_confirmed),
           daemon=True).start()


def send_bot_started_notification_handler(c: Vertex, *args):
    """
    Отправляет уведомление о запуске бота в телеграм.
    """
    if c.telegram is None:
        return
    text = _("fpv_init", c.VERSION, c.account.username, c.account.id,
             c.balance.total_rub, c.balance.total_usd, c.balance.total_eur, c.account.active_sales)
    for i in c.telegram.init_messages:
        try:
            c.telegram.bot.edit_message_text(text, i[0], i[1])
        except:
            continue






BIND_TO_INIT_MESSAGE = [save_init_chats_handler]

BIND_TO_LAST_CHAT_MESSAGE_CHANGED = [old_log_msg_handler,
                                     greetings_handler,
                                     add_old_user_handler,
                                     send_response_handler,
                                     process_review_handler,
                                     old_send_new_msg_notification_handler,
                                     send_command_notification_handler,
                                     test_auto_delivery_handler,]

BIND_TO_NEW_MESSAGE = [log_msg_handler,
                       greetings_handler,
                       add_old_user_handler,
                       send_response_handler,
                       process_review_handler,
                       send_new_msg_notification_handler,
                       send_command_notification_handler,
                       test_auto_delivery_handler,
                       utils.message_hook]

BIND_TO_POST_LOTS_RAISE = [send_categories_raised_notification_handler]

BIND_TO_ORDERS_LIST_CHANGED = [update_current_lots_handler]

BIND_TO_NEW_ORDER = [log_new_order_handler, setup_event_attributes_handler,
                     send_new_order_notification_handler, deliver_product_handler,
                     update_lots_state_handler]

BIND_TO_ORDER_STATUS_CHANGED = [send_thank_u_message_handler, send_order_confirmed_notification_handler]

BIND_TO_POST_DELIVERY = [send_delivery_notification_handler]

BIND_TO_POST_START = [send_bot_started_notification_handler]
