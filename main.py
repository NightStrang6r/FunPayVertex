import time
from pip._internal.cli.main import main

# todo убрать когда-то

try:
    import lxml
except ModuleNotFoundError:
    main(["install", "-U", "lxml>=5.3.0"])
except:
    pass
try:
    import bcrypt
except ModuleNotFoundError:
    main(["install", "-U", "bcrypt>=4.2.0"])
except:
    pass
try:
    import socks
except ModuleNotFoundError:
    main(["install", "-U", "pysocks>=1.7.1"])
except:
    pass
import Utils.vertex_tools
import Utils.config_loader as cfg_loader
from first_setup import first_setup
from colorama import Fore, Style
from Utils.logger import configure_logging
import logging
import colorama
import sys
import os
from vertex import Vertex
import Utils.exceptions as excs
from locales.localizer import Localizer

logo = f"""
{Fore.CYAN}{Style.BRIGHT}███████╗██╗   ██╗███╗   ██╗██████╗  █████╗ ██╗   ██╗                      
██╔════╝██║   ██║████╗  ██║██╔══██╗██╔══██╗╚██╗ ██╔╝                      
█████╗  ██║   ██║██╔██╗ ██║██████╔╝███████║ ╚████╔╝                       
██╔══╝  ██║   ██║██║╚██╗██║██╔═══╝ ██╔══██║  ╚██╔╝                        
██║     ╚██████╔╝██║ ╚████║██║     ██║  ██║   ██║                         
╚═╝      ╚═════╝ ╚═╝  ╚═══╝╚═╝     ╚═╝  ╚═╝   ╚═╝{Style.RESET_ALL}                         
                                                                          
                        {Fore.RED}{Style.BRIGHT}██╗   ██╗███████╗██████╗ ████████╗███████╗██╗  ██╗
                        ██║   ██║██╔════╝██╔══██╗╚══██╔══╝██╔════╝╚██╗██╔╝
                        ██║   ██║█████╗  ██████╔╝   ██║   █████╗   ╚███╔╝ 
                        ╚██╗ ██╔╝██╔══╝  ██╔══██╗   ██║   ██╔══╝   ██╔██╗ 
                         ╚████╔╝ ███████╗██║  ██║   ██║   ███████╗██╔╝ ██╗
                          ╚═══╝  ╚══════╝╚═╝  ╚═╝   ╚═╝   ╚══════╝╚═╝  ╚═╝{Style.RESET_ALL}
"""

VERSION = "2.0.0"

Utils.vertex_tools.set_console_title(f"FunPay Vertex v{VERSION}")

if getattr(sys, 'frozen', False):
    os.chdir(os.path.dirname(sys.executable))
else:
    os.chdir(os.path.dirname(__file__))

folders = ["configs", "logs", "storage", "storage/cache", "storage/plugins", "storage/products", "plugins"]
for i in folders:
    if not os.path.exists(i):
        os.makedirs(i)

files = ["configs/auto_delivery.cfg", "configs/auto_response.cfg"]
for i in files:
    if not os.path.exists(i):
        with open(i, "w", encoding="utf-8") as f:
            ...

colorama.init()

configure_logging()
logging.raiseExceptions = False
logger = logging.getLogger("main")
logger.debug("------------------------------------------------------------------")

print(logo)
print(f"{Fore.RED}{Style.BRIGHT}v{VERSION}{Style.RESET_ALL}\n")
print(f"{Fore.MAGENTA}{Style.BRIGHT}By {Fore.BLUE}{Style.BRIGHT}NightStrang6r{Style.RESET_ALL}")
print(f"{Fore.MAGENTA}{Style.BRIGHT} * GitHub: {Fore.BLUE}{Style.BRIGHT}https://github.com/NightStrang6r/FunPayVertex{Style.RESET_ALL}")
print(f"{Fore.MAGENTA}{Style.BRIGHT} * Telegram: {Fore.BLUE}{Style.BRIGHT}https://t.me/funpayplace")
print(f"{Fore.MAGENTA}{Style.BRIGHT} * Discord: {Fore.BLUE}{Style.BRIGHT}https://dsc.gg/funpay\n")

if not os.path.exists("configs/_main.cfg"):
    first_setup()
    sys.exit()

if sys.platform == "linux" and os.getenv('FPV_IS_RUNNIG_AS_SERVICE', '0') == '1':
    import getpass

    pid = str(os.getpid())
    pidFile = open(f"/run/FunPayVertex/{getpass.getuser()}/FunPayVertex.pid", "w")
    pidFile.write(pid)
    pidFile.close()

    logger.info(f"$GREENPID файл создан, PID процесса: {pid}")  # locale


try:
    logger.info("$MAGENTAЗагружаю конфиг _main.cfg...")  # locale
    MAIN_CFG = cfg_loader.load_main_config("configs/_main.cfg")
    localizer = Localizer(MAIN_CFG["Other"]["language"])
    _ = localizer.translate

    logger.info("$MAGENTAЗагружаю конфиг auto_response.cfg...")  # locale
    AR_CFG = cfg_loader.load_auto_response_config("configs/auto_response.cfg")
    RAW_AR_CFG = cfg_loader.load_raw_auto_response_config("configs/auto_response.cfg")

    logger.info("$MAGENTAЗагружаю конфиг auto_delivery.cfg...")  # locale
    AD_CFG = cfg_loader.load_auto_delivery_config("configs/auto_delivery.cfg")
except excs.ConfigParseError as e:
    logger.error(e)
    logger.error("Завершаю программу...")  # locale
    time.sleep(5)
    sys.exit()
except UnicodeDecodeError:
    logger.error("Произошла ошибка при расшифровке UTF-8. Убедитесь, что кодировка файла = UTF-8, "
                 "а формат конца строк = LF.")  # locale
    logger.error("Завершаю программу...")  # locale
    time.sleep(5)
    sys.exit()
except:
    logger.critical("Произошла непредвиденная ошибка.")  # locale
    logger.warning("TRACEBACK", exc_info=True)
    logger.error("Завершаю программу...")  # locale
    time.sleep(5)
    sys.exit()

localizer = Localizer(MAIN_CFG["Other"]["language"])

try:
    Vertex(MAIN_CFG, AD_CFG, AR_CFG, RAW_AR_CFG, VERSION).init().run()
except KeyboardInterrupt:
    logger.info("Завершаю программу...")  # locale
    sys.exit()
except:
    logger.critical("При работе Вертекса произошла необработанная ошибка.")  # locale
    logger.warning("TRACEBACK", exc_info=True)
    logger.critical("Завершаю программу...")  # locale
    time.sleep(5)
    sys.exit()
