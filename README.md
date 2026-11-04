# DreamLand desktop client

A Windows client for DreamLand MUD, built for screen readers first. It uses
native controls (wxPython), so NVDA, JAWS and Narrator read it like any other
Windows program.

It connects the same way the web client does, over the WebSocket at
wss://dreamland.rocks/dreamland, and uses the server's own data wherever the
web client does:

- Clickable commands in the game text: help topics, item menus, speedwalks,
  room exits and links. Enter on a line runs its command, or opens a menu when
  the line has several. Ctrl+L lists every command in recent output.
- Triggers, key macros and aliases are stored on the game server, shared with
  the web client, per character and per account.
- Game settings are built from the server's own list of options.
- Sounds follow the MUD Sound Protocol. The sound list is taken from the web
  client, and new sounds are downloaded from dreamland.rocks when the game asks
  for them.
- The web client's player script runs here too, in a small JavaScript engine
  (QuickJS) with no access to files or the network: the stock defaults.js from
  dreamland.rocks, or the player's own copy from the game server. That gives
  the keypad movement, the script's commands and its triggers.
- English, Ukrainian and Russian for both the menus and the game.

It also has a few things of its own:

- The game's colours, in a dark theme like the web client's, a light theme or
  the system colours, with any font and size (Ctrl+= and Ctrl+- change the
  size).
- Search in the output (Ctrl+F, then Ctrl+G for older matches and Ctrl+Shift+G
  for newer ones).
- Chat buffers per channel, read with Alt and the arrow keys.
- A speech filter for lines you don't want spoken, and logging the session to
  a text file.
- Auto login, with the password kept in Windows Credential Manager.
- Updates from GitHub releases, checked at start.

Press F1 in the client for every keyboard shortcut.

## Download

Get the zip from the
[latest release](https://github.com/OlegTheSnowman/dreamland-client/releases/latest),
unpack it anywhere and run DreamLand.exe. Nothing needs installing. The client
checks for a new release when it starts and offers to install it; Help, Check
for updates does the same by hand.

## Running from source

```
pip install -r requirements.txt
pythonw dreamland.pyw
```

Settings, command history and variables are saved in
%APPDATA%\DreamLandClient\settings.json, chat history in the chat folder next
to it, session logs in logs, and errors in error.log.

To build the release folder and zip into dist:

```
pip install pyinstaller
python build.py
```

## Tests

```
python -m unittest discover -s tests
```

## Sounds

The bundled sounds come from the mudjs repository and are all CC0. Help, Sound
credits in the client lists each one with its author and source.

## License

GPL-3.0, like the web client mudjs, whose player script (dlclient/defaults.js) is
bundled here and whose behaviour this client follows. The sounds are CC0.
