# Changelog

## 📱 Grindstone on your phone

The big one: **check on your bot from anywhere**. Set it up in 5 minutes with
[docs/PHONE.md](docs/PHONE.md).

- **Watch the game live** on your phone - Data saver, Normal or Smooth, with the data it uses
  shown as you watch. It stops by itself when you lock the phone
- **Start, Pause and Stop** from the phone (Stop asks first - no ending a run by a pocket tap)
- **A phone layout** with what the bot is doing, totals, per-hour rates, XP and levels gained,
  and the activity log. Phones get it automatically; *Full panel* is one tap away
- **Notifications** through the free ntfy app: the bot stopping by itself, problems that need
  you (a frozen game, a step given up, auto login paused, a minimized window), level-ups, and an
  optional progress summary every 1-8 hours. Only status text is sent - never your login
- **Private by design**: reached through Tailscale, so only your own devices can see it - nothing
  is opened to the internet
- The live log now works over https (Tailscale's address) too

### Fixes

- Fish+cook: a fenced-off tree is skipped, and when no tree can be chopped the fire's logs are
  spawned instead (no more "Cooked 0 of 22"). Where that happened, the next loads spawn their
  logs straight away instead of walking at the fence again
- Fish+cook: fish dropped to make room for logs no longer count as cooked ("Cooked 22 of 22
  (2 raw dropped to make room for logs)")
- Losing the game while travelling waits for it instead of ending the run

## More skills, longer routes

- New skills: Herblore, Runecrafting, Agility, Hunter, Slayer and Farming - Autopilot trains them too
- Tools › Skill check: every skill for 2 minutes, then a report of what earned XP
- Reads the game's chat: problems ("You need a Mining level of 15...") show in the log, and a run
  that keeps getting the same refusal stops with it instead of spamming
- Autopilot runs until you press Stop (only Controls' *Stop after* limits it); the panel says why
  a plan or Autopilot as a whole ended
- Longer routes: combat to hill giants, ice warriors, ankou and fire giants; thieving paladins
  and heroes; maples and yews; the Mining guild; harpoon fishing (swordfish, then sharks)
- ★ places are placed on real spawn clusters from the server's data, and a run that finds
  nothing at a ★ place checks it in the game and moves it to its targets
- Fresh accounts: food is topped up before fighting and the starter kit is dropped for room
- Steadier game: the add-on no longer reads the game's caches from outside its own thread
  (the cause of freeze-then-crash in combat); auto login clicks "Click here to play"

## First public release

- 13 skills: woodcutting, fishing (+ cooking), mining, combat, ranged, magic, thieving,
  firemaking, cooking, prayer, fletching, crafting, smithing
- Plans with training routes, lowest-level-first, time limits, resume and self-update
- Built-in ★ training places with an in-game check that corrects them
- Recovery from crashes, stalls, deaths and random events; game restart after a crash
- Reads the game's own data and interfaces through an in-client add-on
- Automatic updates on start-up and an Update button in the panel
