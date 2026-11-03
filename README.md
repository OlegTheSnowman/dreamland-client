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

## Running from source

```
pip install -r requirements.txt
pythonw dreamland.pyw
```

Settings, command history and variables are saved in
%APPDATA%\DreamLandClient\settings.json.

## Tests

```
python -m unittest discover -s tests
```

## Sounds

The bundled sounds come from the mudjs repository and are all CC0. Help, Sound
credits in the client lists each one with its author and source.
