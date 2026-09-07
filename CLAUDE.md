# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

FunPay Vertex — a Python bot that automates a FunPay marketplace seller account (auto-raise lots, auto-reply, auto-delivery of goods, lot restore/deactivate) and exposes a full Telegram control panel. There is no FunPay REST API: everything goes through authenticated HTML scraping of `funpay.com`.

The codebase is Russian — docstrings, comments, log messages and UI text. Match that when adding code.

The credits section in the README records where this code came from — keep it.

Two subsystems were deliberately removed and must not be reintroduced:

- **Announcements** — polled a remote Gist every 10 min and pushed arbitrary text/photos/inline-keyboards into the operator's Telegram.
- **Auto-update** — downloaded a zipball from a third-party repo and unpacked it over the live installation with no checksum or signature check. Only its backup half survives, as `Utils/backup.py`. The bot does not update itself; updates are manual.

As a result the only hosts the code contacts are `funpay.com`, `sfunpay.com` (CDN) and `api.ipify.org` (proxy check). If you add an outbound request to anything else, flag it explicitly.

## Commands

```bash
pip install -U -r requirements.txt
```
Installs dependencies (`Setup.bat` on Windows does exactly this). Target runtime is Python 3.11+.

```bash
python main.py
```
Runs the bot. On first run (no `configs/_main.cfg`) it drops into the interactive `first_setup()` wizard. `Start.bat` is the Windows launcher.

```bash
docker-compose up -d --build
```
Docker run; logs via `docker-compose logs -f`. Configs must already exist — the image cannot run the setup wizard.

There are **no tests, no linter, and no CI**. Verification is manual: run the bot and read `logs/log.log` (DEBUG level, tracebacks land there; the console only shows INFO+). `python -m compileall` catches syntax errors but not broken imports — import the modules to check those.

## Architecture

### Two layers

- **`FunPayAPI/`** — a standalone package with no dependency on the app. `Account` (`account.py`) wraps every site call through `Account.method()`, which injects `golden_key`/`PHPSESSID`/extra cookies, user-agent and proxy, retries 429s, and raises `UnauthorizedError` on 403. `types.py` models chats, messages, orders, lots and profiles; parsing is BeautifulSoup/lxml over funpay.com CSS classes, so site markup changes are the usual cause of breakage.
- **The app** — `main.py` → `vertex.py` (`Vertex`) + `handlers.py` (business logic) + `tg_bot/` (Telegram control panel).

`Vertex` and `Localizer` are singletons via `__new__`; `vertex.get_vertex()` returns the live instance from anywhere.

### Event loop and handler registration

`FunPayAPI.Runner.listen()` polls `POST funpay.com/runner/` every `requestsDelay` seconds, diffs the response against saved state, and yields events (`EventTypes` in `FunPayAPI/common/enums.py`). `Vertex.process_events()` maps each event type to a handler list and runs it.

Handlers are registered by convention, not by decorator: **a module exposes module-level `BIND_TO_*` lists of callables** (`BIND_TO_NEW_ORDER`, `BIND_TO_PRE_INIT`, `BIND_TO_POST_DELIVERY`, `BIND_TO_DELETE`, …; the full set is `Vertex.handler_bind_var_names`). `Vertex.add_handlers_from_plugin(module)` collects them. `handlers.py`, each `tg_bot/*_cp.py`, and every third-party plugin are registered the same way. Handler signature is `(vertex, event)`; `run_handlers` swallows and logs every exception, so a broken handler fails silently apart from the log.

Two things that bite:

- **Handlers in one `BIND_TO_*` list communicate through attributes set on the event object.** `setup_event_attributes_handler` does `setattr(e, "config_section_obj", …)`, `delivered`, `goods_left`, `error`, … and later handlers in `BIND_TO_NEW_ORDER` read them. List order is significant.
- **Message logic is duplicated for two modes.** When `oldMsgGetMode` is `1`, the `Runner` is built with `disable_message_requests=True`: no `NewMessageEvent` is produced and only `LastChatMessageChangedEvent` fires. That is why `handlers.py` binds a near-identical set of handlers to both `BIND_TO_NEW_MESSAGE` and `BIND_TO_LAST_CHAT_MESSAGE_CHANGED`. Changes to message handling usually need to land in both paths.

Threading: `Vertex.run()` starts the raise loop and session-update loop as daemon threads and Telegram polling as another; the main thread stays in `process_events()`. Telegram notifications are typically fired off in their own `Thread`.

### Plugins

`Vertex.load_plugins()` imports every `.py` in `plugins/`, requires metadata fields (`NAME`, `VERSION`, `UUID`, …) with a valid UUID4, and registers the module's `BIND_TO_*` lists with the plugin's UUID attached to each handler. `run_handlers` skips handlers whose plugin is disabled; the disabled set is persisted via `vertex_tools.load_disabled_plugins()`. `tg_bot/plugins_cp.py` is the control panel for install/enable/delete.

Plugins execute arbitrary Python with the bot's privileges — the README warning about untrusted plugins is deliberate, keep it.

**Cardinal compatibility shims.** Third-party plugins written for FunPayCardinal import the pre-rebrand names — `from Utils import cardinal_tools` (a *runtime* import) and `from cardinal import Cardinal` (usually under `TYPE_CHECKING`). Two shims keep those working, so the base is a drop-in replacement for Cardinal and existing plugins need no edits:

- `Utils/cardinal_tools.py` re-exports everything public from `Utils/vertex_tools.py`;
- `cardinal.py` re-exports `Vertex` under the name `Cardinal` (same class object, so `isinstance` still works) plus `get_cardinal`.

Do not delete them without checking `plugins/` for the old names first — a missing import makes `load_plugins` skip the plugin with a single log line, which reads as "the plugin silently stopped working". New code should use the new names.

### Telegram control panel

`tg_bot/bot.py` (`TGBot`) wraps pyTelegramBotAPI and adds: authorization by `secretKey`, per-chat notification toggles (`NotificationTypes` in `tg_bot/utils.py`), and a user-state machine (`set_state`/`get_state`/`clear_state`) used for multi-step input flows.

Each control-panel module (`auto_response_cp`, `auto_delivery_cp`, `config_loader_cp`, `templates_cp`, `plugins_cp`, `file_uploader`, `authorized_users_cp`, `proxy_cp`, `default_cp`) exports `init_*(vertex)` bound via `BIND_TO_PRE_INIT`, and inside registers callbacks with `tg.cbq_handler(handler, filter)` / `tg.msg_handler` / `tg.file_handler`. Callback payloads are `"<CBT constant>:<arg>:<arg>"` where the constants live in `tg_bot/CBT.py` (numeric strings, kept short because Telegram caps callback data at 64 bytes); the same constants double as user-state names. Keep `tg_bot/CBT.py` documentation updated when adding one.

### Configuration

INI files parsed with `configparser` configured as `delimiters=(":",)`, `optionxform = str` (**case-sensitive keys**), interpolation off, UTF-8 + LF required. `Utils/config_loader.py` validates each file against a hardcoded schema and raises `ConfigParseError`; adding a new option means adding it there (and to `first_setup.py`'s `default_config`, plus a migration branch like the existing `# UPDATE` blocks so old configs don't fail validation).

At runtime the parsed `ConfigParser` objects (`MAIN_CFG`, `AD_CFG`, `AR_CFG`, `RAW_AR_CFG`) are the single source of truth: the Telegram panel mutates them in memory and persists with `Vertex.save_config(cfg, path)`. Feature flags are exposed as `Vertex` properties (`autoraise_enabled`, `multidelivery_enabled`, …) — prefer those over reading `MAIN_CFG` directly.

- `configs/auto_delivery.cfg` — one section per lot, matched by **substring**: the first section name contained in the order description wins (`get_lot_config_by_name`), so section order in the file decides ties. `response` is required and must contain `$product` when `productsFileName` is set. The products file is `storage/products/<name>`, one item per line; delivered lines are consumed, and pushed back to the top on send failure.
- `configs/auto_response.cfg` — one section per command, `response` required. A `|` in the section name marks a command *set*, expanded at load time into one section per command.

`configs/`, `storage/`, `logs/` and `plugins/` are gitignored runtime state. The local `configs/_main.cfg` holds a live `golden_key` and Telegram bot token — never echo its contents into commits, PRs, or shared output.

### Message rendering

Outgoing FunPay messages go through `Vertex.send_message()` → `parse_message_entities()`, which splits text into chunks and turns inline markers into separate sends: `$photo=<image_id>` (image), `$sleep=<seconds>` (delay). Text variables (`$username`, `$order_id`, `$date`, `$message_text`, …) are substituted earlier by `format_msg_text` / `format_order_text` in `Utils/vertex_tools.py` — that pair is the authoritative list.

Bot-sent messages are marked two ways, and both matter for loop prevention and for the message badges in Telegram:

- an invisible character prefix — `bot_character` (this bot) vs `old_bot_character` (older bots of the same family), giving `by_bot` / `by_vertex`;
- the uploaded image filename — see the commented block in `FunPayAPI/account.py` around the filename check. Those strings are what other bots actually put in the filename, i.e. wire data, not branding: the block deliberately matches several bot families, so do not "simplify" it into a single condition or rename the values.

### Localization and logging

`locales/ru.py`, `locales/en.py` and `locales/uk.py` are flat modules of `key = "text"` with `{}` placeholders. `Localizer().translate(key, *args, language=None)` — aliased to `_` in every module — formats them; `language=` overrides per call, so **different Telegram users can get different languages**. Plugins register their own strings through `add_translation(uuid, …)` / `plugin_translate(uuid, …)`, namespaced by plugin UUID — that is why the localizer and the plugin system are coupled.

**Any new user-facing string needs the key added to all three files**, otherwise users of the other languages silently get the fallback or the raw key name.

Logging is configured once in `main.py` from `Utils.logger.LOGGER_CONFIG` (loggers: `main`, `FPV`, `FunPayAPI`, `TGBot`; plugin loggers are `FPV.<name>` children). Log messages may embed color tokens — `$YELLOW`, `$MAGENTA`, `$RESET`, … — which the CLI formatter expands and the file formatter strips. Never use `print()` for diagnostics; use the module logger, and `logger.debug("TRACEBACK", exc_info=True)` for stack traces (the established idiom).

### Line endings

The tree carries mixed CRLF/LF. Diffs are unreliable without `diff --strip-trailing-cr`, and a file can look 100% rewritten when it is nearly identical. There is no `.gitattributes` yet — worth adding.
