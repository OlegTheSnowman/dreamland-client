# DreamLand desktop client

A Windows client for [DreamLand](https://dreamland.rocks), a text MUD in English, Ukrainian and Russian. It is built for screen readers first and uses native Windows controls, so NVDA, JAWS and Narrator read it like any other program. Sighted players get the game's colours, a dark or light theme and any font they like.

The client talks to the game exactly as the official web client does, over the same WebSocket, and takes as much as it can from the server and from the web client instead of reimplementing it. When the developers change something in the web client or on the server, this client usually picks it up without an update.

## Download

Get the zip from the [latest release](https://github.com/OlegTheSnowman/dreamland-client/releases/latest), unpack it anywhere and run DreamLand.exe. Nothing needs installing. The client checks for a new release when it starts and offers to install it; Help, Check for updates does the same by hand.

## What it does

The main window has two parts, the game output and the command field, and Tab moves between them. Everything else lives in the menus (Alt) and on shortcut keys. F1 lists every shortcut.

From the game and the web client:

- Clickable commands in the game text, such as help topics, hints, item menus, speedwalks and exits. Enter on a line runs its command or opens a menu when the line has several. Down arrow in an empty command field walks through the commands the game offered recently, reading each with the line it came from.
- Triggers, key macros and aliases, stored on the game server and shared with the web client, per character and per account.
- The game settings window, built from the server's own list of options.
- The web client's player script, run in a small JavaScript engine (QuickJS) with no access to files or the network. It gives the same keypad movement and script commands as the browser. You can edit it here and save it to your account.
- Sounds from the game, following the MUD Sound Protocol, with a volume for each kind of sound.
- The game's own text editor, which opens when you write a note or mail or edit your description.
- Autobuff settings: which buffs autobuff casts, in what order, and your own extra lines.
- The characters on your account, with switching between them without a password.
- Help search (Shift+F1) using the same search code as the website, so results match the site and the game.
- Chat buffers per channel, read with Alt and the arrow keys, and a chat history window.

Lists for finding your way:

- Ctrl+R lists the rooms of the area you are in, with the number of steps to each. Type to filter, Enter walks there.
- Ctrl+E lists every area of the world with its levels, its danger rating and its distance from the Market Square in Midgaard. You can sort by name, level or distance, and type a level number to see the areas for it. Enter walks you there from Midgaard.
- Ctrl+J opens the game guide, built from the DreamLand website and refreshed once a day: zone quests for your level and alignment, weapons and armor you can use (filtered by slot, level range and the stat they raise), your class's skills with the teacher of each, gods and races. Alt+Shift+Q, I, S, G and R open its tabs directly, each where you left it. Enter on a quest, an item or a skill walks you to the zone.
- Ctrl+K finds an item by name in any language and shows its stats and where it comes from.

For reading and comfort:

- Ctrl+1 to Ctrl+0 read the last ten lines of game output.
- Ctrl+F searches the output, Ctrl+G and Ctrl+Shift+G find older and newer matches.
- Ctrl+Space finishes the word you are typing from words in the output.
- A speech filter for lines you don't want spoken, a key to stop speech, and logging the session to a text file.
- Auto login, with the password kept in Windows Credential Manager.

## Running from source

```
pip install -r requirements.txt
pythonw dreamland.pyw
```

Settings, history and variables are kept in %APPDATA%\DreamLandClient\settings.json. Chat history, session logs, cached help and sounds live in folders next to it, and crashes are written to error.log there.

To build the release folder and zip into dist:

```
pip install pyinstaller
python build.py
```

## Tests

```
python -m unittest discover -s tests
```

## Credits and license

The game, its server and the web client mudjs are made by the DreamLand team. This client is not an official part of the game.

GPL-3.0, like mudjs, whose player script (dlclient/defaults.js) is bundled here. The bundled sounds come from the mudjs repository and are CC0; Help, Sound credits in the client names each one's author and source.
