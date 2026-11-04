LANGS = [("en", "English"), ("ua", "Українська"), ("ru", "Русский")]

GAME_MENU_CHOICE = {"en": "1", "ua": "2", "ru": "3"}

STRINGS = {
    "en": {
        "app.title": "DreamLand",
        "output.name": "Game output",
        "input.name": "Command",
        "password.name": "Password (hidden)",
        "menu.game": "&Game",
        "menu.connect": "&Connect\tCtrl+O",
        "menu.disconnect": "&Disconnect\tCtrl+D",
        "menu.links": "Commands in recent &output\tCtrl+L",
        "menu.status": "Read &status\tCtrl+S",
        "menu.exit": "E&xit\tAlt+F4",
        "menu.options": "&Options",
        "menu.language": "&Language",
        "menu.speech": "&Speak incoming text\tCtrl+Shift+S",
        "menu.mute": "&Mute sounds\tCtrl+Shift+M",
        "menu.volume_up": "Volume &up\tCtrl+Shift+Up",
        "menu.volume_down": "Volume &down\tCtrl+Shift+Down",
        "menu.help": "&Help",
        "menu.keys": "&Keyboard shortcuts\tF1",
        "menu.credits": "Sound &credits",
        "state.connecting": "Connecting to DreamLand...",
        "state.reconnecting": "Connection lost, coming back into the game...",
        "state.open": "Connected.",
        "state.closed": "Disconnected. Press Ctrl+O to connect again.",
        "state.version": "This client speaks protocol %s, the server speaks %s. Some things may not work.",
        "links.title": "Commands in recent output",
        "links.label": "Commands, newest first",
        "links.none": "No commands on this line.",
        "links.empty": "No clickable commands yet.",
        "links.open": "Opening in your browser: %s",
        "confirm.craft": "Start crafting? This uses up the ingredients.",
        "confirm.title": "Confirm",
        "status.none": "No status yet.",
        "recent.none": "No line there yet.",
        "complete.none": "Nothing to complete.",
        "status.line": "Health %s of %s, mana %s of %s, moves %s of %s.",
        "status.fighting": "Fighting.",
        "speech.on": "Speech on.",
        "speech.off": "Speech off.",
        "menu.echo": "Show sent &commands in the output	Ctrl+Shift+E",
        "echo.on": "Sent commands are shown in the output.",
        "echo.off": "Sent commands are hidden from the output.",
        "menu.defkeys": "Run the web client's player &script (keypad, script commands and triggers)\tCtrl+Shift+W",
        "script.error": "The player script did not load: %s",
        "defkeys.on": "Player script on.",
        "defkeys.off": "Player script off.",
        "sound.muted": "Sounds muted.",
        "sound.unmuted": "Sounds on.",
        "sound.volume": "Volume %d percent.",
        "lang.later": "The game language changes on the next connection. The menus have changed already.",
        "keys.title": "Keyboard shortcuts",
        "keys.text": (
            "Enter in the command field sends the command. Up and Down arrows go through earlier commands.\n"
            "Tab and Shift+Tab move between the game output and the command field. Alt opens the menus.\n"
            "In the game output, Enter on a line runs its command, or opens a menu when the line has several.\n"
            "The Applications key or Shift+F10 in the output always opens that menu.\n"
            "Ctrl+L lists the clickable commands from recent output. Ctrl+R lists the rooms of the area you are in, from the web map; type to search, Enter walks there. When a run stops, Ctrl+Shift+R continues it.\n"
            "Chat buffers: Alt+Left and Alt+Right switch between all chat, tells, group and each channel; Alt+Up and Alt+Down read older and newer messages, Alt+End the newest. Ctrl+H opens the chat history.\n"
            "Ctrl+S reads health, mana and moves.\n"
            "Ctrl+Space finishes the word you are typing from words in the output, newest first; press again for the next one, and after the last it goes back to what you typed.\n"
            "Down arrow in an empty command field fills in the newest command the game offered, such as a hint; more Down presses go to older ones, Up comes back.\n"
            "The web client's player script runs here too: by default keypad 8, 2, 4, 6, 9 and 1 walk north, south, west, east, up and down, 5 scans, Alt plus a direction scans that way, and the tilde key starts autobuff. Your own script, if you edited it in the web client, comes from the game server. Ctrl+Shift+W turns the script off.\n"
            "Ctrl+1 to Ctrl+9 read the 1st to 9th line from the end of the output, Ctrl+0 the 10th.\n"
            "Ctrl+Shift+S turns speech of incoming text on and off.\n"
            "Ctrl+Shift+M mutes sounds. Ctrl+Shift+Up and Down change the volume.\n"
            "Ctrl+O connects, Ctrl+D disconnects, Ctrl+Shift+L sets up auto login.\n"
            "Escape in the command field clears it.\n"
            "Ctrl+Shift+T triggers, Ctrl+Shift+K key macros, Ctrl+Shift+A aliases, Ctrl+Shift+O game settings.\n"
            "Triggers, key macros and aliases are kept on the game server and shared with the web client.\n"
            "In the command field: #var name value sets a variable, #hotkey f1 command sets a key, #5 command repeats a command."
        ),
        "credits.title": "Sound credits",
        "ok": "OK",
        "cancel": "Cancel",
    },
    "ua": {
        "app.title": "DreamLand",
        "output.name": "Вивід гри",
        "input.name": "Команда",
        "password.name": "Пароль (прихований)",
        "menu.game": "&Гра",
        "menu.connect": "&Підключитися\tCtrl+O",
        "menu.disconnect": "&Відключитися\tCtrl+D",
        "menu.links": "Команди в останньому &виводі\tCtrl+L",
        "menu.status": "Прочитати &стан\tCtrl+S",
        "menu.exit": "&Вийти\tAlt+F4",
        "menu.options": "&Налаштування",
        "menu.language": "&Мова",
        "menu.speech": "&Озвучувати вхідний текст\tCtrl+Shift+S",
        "menu.mute": "&Вимкнути звуки\tCtrl+Shift+M",
        "menu.volume_up": "&Гучніше\tCtrl+Shift+Up",
        "menu.volume_down": "&Тихіше\tCtrl+Shift+Down",
        "menu.help": "&Довідка",
        "menu.keys": "&Клавіші\tF1",
        "menu.credits": "&Автори звуків",
        "state.connecting": "Підключення до DreamLand...",
        "state.reconnecting": "Зʼєднання втрачено, повертаємося в гру...",
        "state.open": "Підключено.",
        "state.closed": "Відключено. Натисни Ctrl+O, щоб підключитися знову.",
        "state.version": "Цей клієнт говорить протоколом %s, сервер протоколом %s. Дещо може не працювати.",
        "links.title": "Команди в останньому виводі",
        "links.label": "Команди, найновіші зверху",
        "links.none": "У цьому рядку немає команд.",
        "links.empty": "Поки що немає команд.",
        "links.open": "Відкриваю в браузері: %s",
        "confirm.craft": "Почати виготовлення? Інгредієнти буде витрачено.",
        "confirm.title": "Підтвердження",
        "status.none": "Стану ще немає.",
        "recent.none": "Такого рядка ще немає.",
        "complete.none": "Нічого доповнити.",
        "status.line": "Здоровʼя %s з %s, мана %s з %s, рухи %s з %s.",
        "status.fighting": "У бою.",
        "speech.on": "Озвучення увімкнено.",
        "speech.off": "Озвучення вимкнено.",
        "menu.echo": "Показувати надіслані &команди у виводі	Ctrl+Shift+E",
        "echo.on": "Надіслані команди показуються у виводі.",
        "echo.off": "Надіслані команди приховано з виводу.",
        "menu.defkeys": "Виконувати &скрипт гравця з веб-клієнта (цифрова клавіатура, команди і тригери скрипту)\tCtrl+Shift+W",
        "script.error": "Скрипт гравця не завантажився: %s",
        "defkeys.on": "Скрипт гравця увімкнено.",
        "defkeys.off": "Скрипт гравця вимкнено.",
        "sound.muted": "Звуки вимкнено.",
        "sound.unmuted": "Звуки увімкнено.",
        "sound.volume": "Гучність %d відсотків.",
        "lang.later": "Мова гри зміниться при наступному підключенні. Меню вже змінилися.",
        "keys.title": "Клавіші",
        "keys.text": (
            "Enter у полі команди надсилає команду. Стрілки вгору і вниз гортають попередні команди.\n"
            "Tab і Shift+Tab перемикають між виводом гри і полем команди. Alt відкриває меню.\n"
            "У виводі гри Enter на рядку виконує його команду або відкриває меню, якщо команд кілька.\n"
            "Клавіша контекстного меню або Shift+F10 у виводі завжди відкриває це меню.\n"
            "Ctrl+L показує команди з останнього виводу. Ctrl+R показує кімнати зони, де ти є, з веб-мапи; пиши для пошуку, Enter веде туди. Якщо біг перервано, Ctrl+Shift+R продовжує його.\n"
            "Буфери чату: Alt+стрілки вліво і вправо перемикають між усім чатом, особистими, групою і кожним каналом; Alt+стрілки вгору і вниз читають старіші й новіші повідомлення, Alt+End найновіше. Ctrl+H відкриває історію чату.\n"
            "Ctrl+S читає здоровʼя, ману і рухи.\n"
            "Ctrl+пробіл доповнює слово, яке ти набираєш, словами з виводу, найновіші першими; ще раз - наступне, після останнього повертається набране.\n"
            "Стрілка вниз у порожньому полі команди підставляє найновішу команду, яку запропонувала гра, наприклад підказку; ще раз вниз - старіші, вгору - назад.\n"
            "Тут працює і скрипт гравця з веб-клієнта: типово цифрова клавіатура 8, 2, 4, 6, 9 і 1 веде на північ, південь, захід, схід, вгору і вниз, 5 оглядає, Alt з напрямком оглядає в той бік, тильда запускає автобаф. Твій власний скрипт, якщо ти змінював його у веб-клієнті, береться з сервера гри. Ctrl+Shift+W вимикає скрипт.\n"
            "Ctrl+1..Ctrl+9 читають 1-й..9-й рядок з кінця виводу, Ctrl+0 10-й.\n"
            "Ctrl+Shift+S вмикає і вимикає озвучення вхідного тексту.\n"
            "Ctrl+Shift+M вимикає звуки. Ctrl+Shift+стрілки вгору і вниз змінюють гучність.\n"
            "Ctrl+O підключає, Ctrl+D відключає, Ctrl+Shift+L налаштовує автовхід.\n"
            "Escape у полі команди очищає його.\n"
            "Ctrl+Shift+T тригери, Ctrl+Shift+K макроси клавіш, Ctrl+Shift+A синоніми, Ctrl+Shift+O налаштування гри.\n"
            "Тригери, макроси і синоніми зберігаються на сервері гри і спільні з веб-клієнтом.\n"
            "У полі команди: #var імʼя значення задає змінну, #hotkey f1 команда задає клавішу, #5 команда повторює команду."
        ),
        "credits.title": "Автори звуків",
        "ok": "Гаразд",
        "cancel": "Скасувати",
    },
    "ru": {
        "app.title": "DreamLand",
        "output.name": "Вывод игры",
        "input.name": "Команда",
        "password.name": "Пароль (скрыт)",
        "menu.game": "&Игра",
        "menu.connect": "&Подключиться\tCtrl+O",
        "menu.disconnect": "&Отключиться\tCtrl+D",
        "menu.links": "Команды в последнем &выводе\tCtrl+L",
        "menu.status": "Прочитать &состояние\tCtrl+S",
        "menu.exit": "В&ыход\tAlt+F4",
        "menu.options": "&Настройки",
        "menu.language": "&Язык",
        "menu.speech": "&Озвучивать входящий текст\tCtrl+Shift+S",
        "menu.mute": "&Выключить звуки\tCtrl+Shift+M",
        "menu.volume_up": "&Громче\tCtrl+Shift+Up",
        "menu.volume_down": "&Тише\tCtrl+Shift+Down",
        "menu.help": "&Справка",
        "menu.keys": "&Клавиши\tF1",
        "menu.credits": "&Авторы звуков",
        "state.connecting": "Подключение к DreamLand...",
        "state.reconnecting": "Связь потеряна, возвращаемся в игру...",
        "state.open": "Подключено.",
        "state.closed": "Отключено. Нажми Ctrl+O, чтобы подключиться снова.",
        "state.version": "Этот клиент говорит протоколом %s, сервер протоколом %s. Что-то может не работать.",
        "links.title": "Команды в последнем выводе",
        "links.label": "Команды, новые сверху",
        "links.none": "В этой строке нет команд.",
        "links.empty": "Пока нет команд.",
        "links.open": "Открываю в браузере: %s",
        "confirm.craft": "Начать изготовление? Ингредиенты будут потрачены.",
        "confirm.title": "Подтверждение",
        "status.none": "Состояния еще нет.",
        "recent.none": "Такой строки еще нет.",
        "complete.none": "Нечего дополнить.",
        "status.line": "Здоровье %s из %s, мана %s из %s, движение %s из %s.",
        "status.fighting": "В бою.",
        "speech.on": "Озвучка включена.",
        "speech.off": "Озвучка выключена.",
        "menu.echo": "Показывать отправленные &команды в выводе	Ctrl+Shift+E",
        "echo.on": "Отправленные команды показываются в выводе.",
        "echo.off": "Отправленные команды скрыты из вывода.",
        "menu.defkeys": "Выполнять &скрипт игрока из веб-клиента (цифровая клавиатура, команды и триггеры скрипта)\tCtrl+Shift+W",
        "script.error": "Скрипт игрока не загрузился: %s",
        "defkeys.on": "Скрипт игрока включен.",
        "defkeys.off": "Скрипт игрока выключен.",
        "sound.muted": "Звуки выключены.",
        "sound.unmuted": "Звуки включены.",
        "sound.volume": "Громкость %d процентов.",
        "lang.later": "Язык игры сменится при следующем подключении. Меню уже сменились.",
        "keys.title": "Клавиши",
        "keys.text": (
            "Enter в поле команды отправляет команду. Стрелки вверх и вниз листают прежние команды.\n"
            "Tab и Shift+Tab переключают между выводом игры и полем команды. Alt открывает меню.\n"
            "В выводе игры Enter на строке выполняет ее команду или открывает меню, если команд несколько.\n"
            "Клавиша контекстного меню или Shift+F10 в выводе всегда открывает это меню.\n"
            "Ctrl+L показывает команды из последнего вывода. Ctrl+R показывает комнаты зоны, где ты находишься, с веб-карты; пиши для поиска, Enter ведет туда. Если бег прерван, Ctrl+Shift+R продолжает его.\n"
            "Буферы чата: Alt+стрелки влево и вправо переключают между всем чатом, личными, группой и каждым каналом; Alt+стрелки вверх и вниз читают более старые и новые сообщения, Alt+End самое новое. Ctrl+H открывает историю чата.\n"
            "Ctrl+S читает здоровье, ману и движение.\n"
            "Ctrl+пробел дополняет набираемое слово словами из вывода, самые новые первыми; еще раз - следующее, после последнего возвращается набранное.\n"
            "Стрелка вниз в пустом поле команды подставляет самую новую команду, которую предложила игра, например подсказку; еще раз вниз - более старые, вверх - назад.\n"
            "Здесь работает и скрипт игрока из веб-клиента: по умолчанию цифровая клавиатура 8, 2, 4, 6, 9 и 1 ведет на север, юг, запад, восток, вверх и вниз, 5 осматривает, Alt с направлением осматривает в ту сторону, тильда запускает автобафф. Твой собственный скрипт, если ты менял его в веб-клиенте, берется с сервера игры. Ctrl+Shift+W выключает скрипт.\n"
            "Ctrl+1..Ctrl+9 читают 1-ю..9-ю строку с конца вывода, Ctrl+0 10-ю.\n"
            "Ctrl+Shift+S включает и выключает озвучку входящего текста.\n"
            "Ctrl+Shift+M выключает звуки. Ctrl+Shift+стрелки вверх и вниз меняют громкость.\n"
            "Ctrl+O подключает, Ctrl+D отключает, Ctrl+Shift+L настраивает автовход.\n"
            "Escape в поле команды очищает его.\n"
            "Ctrl+Shift+T триггеры, Ctrl+Shift+K макросы клавиш, Ctrl+Shift+A синонимы, Ctrl+Shift+O настройки игры.\n"
            "Триггеры, макросы и синонимы хранятся на сервере игры и общие с веб-клиентом.\n"
            "В поле команды: #var имя значение задает переменную, #hotkey f1 команда задает клавишу, #5 команда повторяет команду."
        ),
        "credits.title": "Авторы звуков",
        "ok": "ОК",
        "cancel": "Отмена",
    },
}


from .i18n_tools import TOOLS

from .i18n_extra import EXTRA

for _lang, _strings in TOOLS.items():
    STRINGS[_lang].update(_strings)
for _lang, _strings in EXTRA.items():
    STRINGS[_lang].update(_strings)
    STRINGS[_lang]["keys.text"] += _strings["keys.extra"] + _strings["keys.areas"] + _strings["keys.help"] + _strings["keys.four"] + _strings["keys.status"] + _strings["keys.tones"] + _strings["keys.room"] + _strings["keys.typed"]


class Tr:
    def __init__(self, lang="en"):
        self.lang = lang if lang in STRINGS else "en"

    def __call__(self, key, *args):
        s = STRINGS[self.lang].get(key) or STRINGS["en"].get(key, key)
        return s % args if args else s
