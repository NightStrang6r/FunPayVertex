from __future__ import annotations
from typing import TYPE_CHECKING, Callable
if TYPE_CHECKING:
    from configparser import ConfigParser

from types import ModuleType
import configparser
import requests
import datetime
import logging
import random
import time
import sys

import FunPayAPI
from locales.localizer import Localizer

from Utils import vertex_tools

from threading import Thread


logger = logging.getLogger("FPV")
localizer = Localizer()
_ = localizer.translate


def check_proxy(proxy: dict) -> bool:
    """
    Проверяет работоспособность прокси.

    :param proxy: словарь с данными прокси.

    :return: True, если прокси работает, иначе - False.
    """
    logger.info(_("crd_checking_proxy"))
    try:
        response = requests.get("https://api.ipify.org/", proxies=proxy, timeout=10.0)
    except:
        logger.error(_("crd_proxy_err"))
        logger.debug("TRACEBACK", exc_info=True)
        return False
    logger.info(_("crd_proxy_success", response.content.decode()))
    return True


def get_vertex() -> None | Vertex:
    """
    Возвращает существующий экземпляр вертекса.
    """
    if hasattr(Vertex, "instance"):
        return getattr(Vertex, "instance")

class Vertex(object):
    def __new__(cls, *args, **kwargs):
        if not hasattr(cls, "instance"):
            cls.instance = super(Vertex, cls).__new__(cls)
        return getattr(cls, "instance")

    def __init__(self, main_config: ConfigParser, version: str):
        self.VERSION = version
        self.instance_id = random.randint(0, 999999999)
        self.delivery_tests = {}  # Одноразовые ключи для тестов автовыдачи. {"ключ": "название лота"}

        # Конфиги
        self.MAIN_CFG = main_config

        # Прокси
        self.proxy = {}
        if self.MAIN_CFG["Proxy"].getboolean("enable"):
            if self.MAIN_CFG["Proxy"]["ip"] and self.MAIN_CFG["Proxy"]["port"].isnumeric():
                logger.info(_("crd_proxy_detected"))

                ip, port = self.MAIN_CFG["Proxy"]["ip"], self.MAIN_CFG["Proxy"]["port"]
                login, password = self.MAIN_CFG["Proxy"]["login"], self.MAIN_CFG["Proxy"]["password"]
                self.proxy = {
                    "http": f"http://{f'{login}:{password}@' if login and password else ''}{ip}:{port}",
                    "https": f"http://{f'{login}:{password}@' if login and password else ''}{ip}:{port}"
                }
                if self.MAIN_CFG["Proxy"].getboolean("check") and not check_proxy(self.proxy):
                    sys.exit()

        self.account = FunPayAPI.Account(self.MAIN_CFG["FunPay"]["golden_key"],
                                         self.MAIN_CFG["FunPay"]["user_agent"],
                                         proxy=self.proxy)
        self.runner: FunPayAPI.Runner | None = None

        self.running = False
        self.run_id = 0
        self.start_time = int(time.time())

        self.balance: FunPayAPI.types.Balance | None = None
        self.raise_time = {}  # Временные метки поднятия категорий {id игры: след. время поднятия}
        self.profile: FunPayAPI.types.UserProfile | None = None  # FunPay профиль для всего вертекса (+ хэндлеров)
        self.last_tg_profile_update = datetime.datetime.now()  # Последнее время обновления профиля для TG-ПУ
        self.curr_profile: FunPayAPI.types.UserProfile | None = None  # Текущий профиль (для восст. / деакт. лотов.)
        # Тег последнего event'а, после которого обновлялся self.current_profile
        self.curr_profile_last_tag: str | None = None
        # Тег последнего event'а, после которого обновлялось состояние лотов.
        self.last_state_change_tag: str | None = None

    def __init_account(self) -> None:
        """
        Инициализирует класс аккаунта (self.account)
        """
        while True:
            try:
                self.account.get()
                self.balance = self.get_balance()
                greeting_text = vertex_tools.create_greeting_text(self)
                for line in greeting_text.split("\n"):
                    logger.info(line)
                break
            except TimeoutError:
                logger.error(_("crd_acc_get_timeout_err"))
            except (FunPayAPI.exceptions.UnauthorizedError, FunPayAPI.exceptions.RequestFailedError) as e:
                logger.error(e.short_str())
                logger.debug(e)
            except:
                logger.error(_("crd_acc_get_unexpected_err"))
                logger.debug("TRACEBACK", exc_info=True)
            logger.warning(_("crd_try_again_in_n_secs", 2))
            time.sleep(2)

    def __update_profile(self, infinite_polling: bool = True, attempts: int = 0, update_main_profile: bool = True) -> bool:
        """
        Загружает данные о лотах категориях аккаунта

        :param infinite_polling: бесконечно посылать запросы, пока не будет получен ответ (игнорировать макс. кол-во
        попыток)
        :param attempts: максимальное кол-во попыток.
        :param update_telegram_profile: обновить ли информацию о профиле для TG ПУ?
        :param update_main_profile: обновить ли информацию о профиле для всего вертекса (+ хэндлеров)?

        :return: True, если информация обновлена, False, если превышено макс. кол-во попыток.
        """
        logger.info(_("crd_getting_profile_data"))
        # Получаем категории аккаунта.
        while attempts or infinite_polling:
            try:
                profile = self.account.get_user(self.account.id)
                break
            except TimeoutError:
                logger.error(_("crd_profile_get_timeout_err"))
            except FunPayAPI.exceptions.RequestFailedError as e:
                logger.error(e.short_str())
                logger.debug(e)
            except:
                logger.error(_("crd_profile_get_unexpected_err"))
                logger.debug("TRACEBACK", exc_info=True)
            attempts -= 1
            logger.warning(_("crd_try_again_in_n_secs", 2))
            time.sleep(2)
        else:
            logger.error(_("crd_profile_get_too_many_attempts_err", attempts))
            return False

        if update_main_profile:
            self.profile = profile
            self.curr_profile = profile
            self.lots_ids = [i.id for i in profile.get_lots()]
            logger.info(_("crd_profile_updated", len(profile.get_lots()), len(profile.get_sorted_lots(2))))
        return True

    def get_balance(self, attempts: int = 3) -> FunPayAPI.types.Balance:
        subcategories = self.account.get_sorted_subcategories()[FunPayAPI.enums.SubCategoryTypes.COMMON]
        lots = []
        while not lots and attempts:
            attempts -= 1
            subcat_id = random.choice(list(subcategories.keys()))
            lots = self.account.get_subcategory_public_lots(FunPayAPI.enums.SubCategoryTypes.COMMON, subcat_id)
            break
        else:
            raise Exception(...)
        balance = self.account.get_balance(random.choice(lots).id)
        return balance

    # Прочее
    def raise_lots(self) -> int:
        """
        Пытается поднять лоты.

        :return: предположительное время, когда нужно снова запустить данную функцию.
        """
        # Время следующего вызова функции (по умолчанию - бесконечность).
        next_call = float("inf")

        for subcat in self.profile.get_sorted_lots(2):
            # Если id категории текущей подкатегории уже находится в self.game_ids, но время поднятия подкатегорий
            # данной категории еще не настало - пропускам эту подкатегорию.
            if (saved_time := self.raise_time.get(subcat.category.id)) and saved_time > int(time.time()):
                # Если записанное в self.game_ids время больше текущего времени
                # обновляем время next_call'а на записанное время.
                next_call = saved_time if saved_time < next_call else next_call
                continue

            # В любом другом случае пытаемся поднять лоты всех категорий, относящихся к игре
            try:
                time.sleep(0.5)
                self.account.raise_lots(subcat.category.id)
            except FunPayAPI.exceptions.RaiseError as e:
                if e.wait_time is not None:
                    logger.warning(_("crd_raise_time_err", subcat.category.name, vertex_tools.time_to_str(e.wait_time)))
                    next_time = int(time.time()) + e.wait_time
                else:
                    logger.error(_("crd_raise_unexpected_err", subcat.category.name))
                    next_time = int(time.time()) + 10
                self.raise_time[subcat.category.id] = next_time
                next_call = next_time if next_time < next_call else next_call
                continue
            except Exception as e:
                if isinstance(e, FunPayAPI.exceptions.RequestFailedError) and e.status_code == 429:
                    logger.warning(_("crd_raise_429_err", subcat.category.name))
                    time.sleep(10)
                    next_time = int(time.time()) + 1
                else:
                    logger.error(_("crd_raise_unexpected_err", subcat.category.name))
                    logger.debug("TRACEBACK", exc_info=True)
                    next_time = int(time.time()) + 10
                next_call = next_time if next_time < next_call else next_call
                continue

            logger.info(_("crd_lots_raised", subcat.category.name))
            logger.info(_("crd_raise_wait_3600", vertex_tools.time_to_str(3600)))
            next_time = int(time.time()) + 3600
            self.raise_time[subcat.category.id] = next_time
            next_call = next_time if next_time < next_call else next_call
            self.run_handlers(self.post_lots_raise_handlers, (self, subcat.category))
        return next_call if next_call < float("inf") else 10

    def update_session(self, attempts: int = 3) -> bool:
        """
        Обновляет данные аккаунта (баланс, токены и т.д.)

        :param attempts: кол-во попыток.

        :return: True, если удалось обновить данные, False - если нет.
        """
        while attempts:
            try:
                self.account.get(update_phpsessid=True)
                logger.info(_("crd_session_updated"))
                return True
            except TimeoutError:
                logger.warning(_("crd_session_timeout_err"))
            except (FunPayAPI.exceptions.UnauthorizedError, FunPayAPI.exceptions.RequestFailedError) as e:
                logger.error(e.short_str)
                logger.debug(e)
            except:
                logger.error(_("crd_session_unexpected_err"))
                logger.debug("TRACEBACK", exc_info=True)
            attempts -= 1
            logger.warning(_("crd_try_again_in_n_secs", 2))
            time.sleep(2)
        else:
            logger.error(_("crd_session_no_more_attempts_err"))
            return False

    def lots_raise_loop(self):
        """
        Запускает бесконечный цикл поднятия категорий (если autoRaise в _main.cfg == 1)
        """
        if not self.profile.get_lots():
            logger.info(_("crd_raise_loop_not_started"))
            return

        logger.info(_("crd_raise_loop_started"))
        while True:
            try:
                if not self.MAIN_CFG["FunPay"].getboolean("autoRaise"):
                    time.sleep(10)
                    continue
                next_time = self.raise_lots()
                delay = next_time - int(time.time())
                if delay <= 0:
                    continue
                time.sleep(delay)
            except:
                logger.debug("TRACEBACK", exc_info=True)

    def update_session_loop(self):
        """
        Запускает бесконечный цикл обновления данных о пользователе.
        """
        logger.info(_("crd_session_loop_started"))
        sleep_time = 3600
        while True:
            time.sleep(sleep_time)
            result = self.update_session()
            sleep_time = 60 if not result else 3600

    # Управление процессом
    def init(self):
        """
        Инициализирует вертекс: получает данные аккаунта и профиля.
        """
        self.__init_account()
        self.runner = FunPayAPI.Runner(self.account, True)
        self.__update_profile()
        return self

    def run(self):
        """
        Запускает вертекс после инициализации. Используется для первого старта.
        """
        self.run_id += 1
        self.start_time = int(time.time())

        lots_raise_loop = Thread(target=self.lots_raise_loop, daemon=True)
        lots_raise_loop.start()

        update_session_loop = Thread(target=self.update_session_loop, daemon=True)
        update_session_loop.start()

        lots_raise_loop.join()
        update_session_loop.join()

    @staticmethod
    def save_config(config: configparser.ConfigParser, file_path: str) -> None:
        """
        Сохраняет конфиг в указанный файл.

        :param config: объект конфига.
        :param file_path: путь до файла, в который нужно сохранить конфиг.
        """
        with open(file_path, "w", encoding="utf-8") as f:
            config.write(f)


    # Настройки
    @property
    def autoraise_enabled(self) -> bool:
        return self.MAIN_CFG["FunPay"].getboolean("autoRaise")