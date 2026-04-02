"""
Patch script: adds Telegram proxy support to FunPayVertex.

Patches:
  - first_setup.py         — adds "proxy": "" to default Telegram config
  - Utils/config_loader.py — adds proxy validation + auto-migration
  - tg_bot/bot.py          — applies proxy to telebot.apihelper at startup
  - setup.py               — adds PySocks dependency
  - configs/_main.cfg      — adds proxy key to [Telegram] section (if file exists)

Run from the scripts/ directory (it resolves paths relative to project root automatically).
"""

import os
import sys
import shutil
import subprocess
import configparser

# ── helpers ──────────────────────────────────────────────────────────────────

def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def write(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def backup(path):
    dst = path + ".bak"
    shutil.copy2(path, dst)
    print(f"  [backup] {dst}")

def patch_file(path, old, new, label):
    content = read(path)
    if new in content:
        print(f"  [skip]   {path}  ({label} already applied)")
        return False
    if old not in content:
        print(f"  [ERROR]  {path}  — expected text not found for: {label}")
        print(f"           The file may have been modified. Apply this patch manually.")
        return False
    backup(path)
    write(path, content.replace(old, new, 1))
    print(f"  [ok]     {path}  ({label})")
    return True

# ── patches ──────────────────────────────────────────────────────────────────

PATCHES = [
    (
        "first_setup.py",
        # old
        '    "Telegram": {\n'
        '        "enabled": "0",\n'
        '        "token": "",\n'
        '        "secretKey": "СекретныйПароль"\n'
        '    },',
        # new
        '    "Telegram": {\n'
        '        "enabled": "0",\n'
        '        "token": "",\n'
        '        "secretKey": "СекретныйПароль",\n'
        '        "proxy": ""\n'
        '    },',
        "add proxy to default config",
    ),
    (
        "Utils/config_loader.py",
        # old
        '        "Telegram": {\n'
        '            "enabled": ["0", "1"],\n'
        '            "token": "any+empty",\n'
        '            "secretKey": "any"\n'
        '        },',
        # new
        '        "Telegram": {\n'
        '            "enabled": ["0", "1"],\n'
        '            "token": "any+empty",\n'
        '            "secretKey": "any",\n'
        '            "proxy": "any+empty"\n'
        '        },',
        "add proxy to Telegram validation",
    ),
    (
        "Utils/config_loader.py",
        # old
        '            # END OF UPDATE 009\n',
        # new
        '            # END OF UPDATE 009\n'
        '            elif section_name == "Telegram" and param_name == "proxy" and param_name not in config[section_name]:\n'
        '                config.set("Telegram", "proxy", "")\n'
        '                with open("configs/_main.cfg", "w", encoding="utf-8") as f:\n'
        '                    config.write(f)\n',
        "add proxy migration for existing configs",
    ),
    (
        "tg_bot/bot.py",
        # old
        '        self.bot = telebot.TeleBot(self.vertex.MAIN_CFG["Telegram"]["token"], parse_mode="HTML",\n'
        '                                   allow_sending_without_reply=True, num_threads=5)\n'
        '\n'
        '        self.file_handlers = {}',
        # new
        '        self.bot = telebot.TeleBot(self.vertex.MAIN_CFG["Telegram"]["token"], parse_mode="HTML",\n'
        '                                   allow_sending_without_reply=True, num_threads=5)\n'
        '\n'
        '        tg_proxy = self.vertex.MAIN_CFG["Telegram"].get("proxy", "").strip()\n'
        '        if tg_proxy:\n'
        '            telebot.apihelper.proxy = {"https": tg_proxy}\n'
        '\n'
        '        self.file_handlers = {}',
        "apply proxy to telebot.apihelper",
    ),
    (
        "setup.py",
        # old
        '    "requests_toolbelt==0.10.1"\n'
        ']',
        # new
        '    "requests_toolbelt==0.10.1",\n'
        '    "PySocks>=1.7.1"\n'
        ']',
        "add PySocks dependency",
    ),
]

# ── _main.cfg patch (configparser-based, values vary per user) ────────────────

def patch_main_cfg(path):
    if not os.path.exists(path):
        print(f"  [skip]   {path}  (file not found — proxy will be added on first bot run)")
        return
    cfg = configparser.ConfigParser(delimiters=(":",), interpolation=None)
    cfg.optionxform = str
    with open(path, "r", encoding="utf-8") as f:
        cfg.read_file(f)
    if "Telegram" not in cfg.sections():
        print(f"  [skip]   {path}  (no [Telegram] section)")
        return
    if "proxy" in cfg["Telegram"]:
        print(f"  [skip]   {path}  (proxy already present in [Telegram])")
        return
    backup(path)
    cfg.set("Telegram", "proxy", "")
    with open(path, "w", encoding="utf-8") as f:
        cfg.write(f)
    print(f"  [ok]     {path}  (added proxy to [Telegram])")

# ── main ─────────────────────────────────────────────────────────────────────

def main():
    # Resolve project root (one level above this script's directory)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(script_dir)
    os.chdir(root)

    print("\n=== FunPayVertex — Telegram proxy patch ===\n")

    missing = [p[0] for p in PATCHES if not os.path.exists(p[0])]
    if missing:
        print("ERROR: The following required files were not found:")
        for f in set(missing):
            print(f"  {f}")
        print(f"\nProject root resolved to: {root}")
        print("Make sure the scripts/ folder is inside the FunPayVertex root directory.")
        sys.exit(1)

    print("Patching source files...\n")
    for path, old, new, label in PATCHES:
        patch_file(path, old, new, label)
    patch_main_cfg("configs/_main.cfg")

    print("\nInstalling PySocks...\n")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-U", "PySocks>=1.7.1"])
        print("\n  [ok]     PySocks installed")
    except subprocess.CalledProcessError:
        print("\n  [ERROR]  pip install failed — install manually: pip install PySocks")

    print("\n=== Done! ===")
    print("\nTo use a Telegram proxy, set in configs/_main.cfg:")
    print("  [Telegram]")
    print("  proxy : socks5://login:password@ip:port")
    print("  # or:  proxy : http://login:password@ip:port")
    print("  # leave empty to disable proxy\n")


if __name__ == "__main__":
    main()
