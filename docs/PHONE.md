# Grindstone on your phone

Check on the bot and start, pause or stop it from your phone, even when you're out, and get a
notification when something needs you.

The panel has no password and can control your game, so **never** open its port on your router
or put it on a public tunnel (ngrok, Tailscale Funnel...). Tailscale keeps it private: only your
own devices can reach it.

## 1. Reach the panel with Tailscale

1. Install [Tailscale](https://tailscale.com/download) on the PC and on your phone, and sign in to
   the same account on both.
2. On the PC, open Command Prompt and run:
   ```
   tailscale serve --bg 8765
   ```
   It prints your panel's private address, like `https://my-pc.tail1234.ts.net`. This only needs
   doing once - it comes back after a restart.
3. On your phone (Tailscale switched on), open that address. Phones get the **phone layout**
   (`/m`); *Full panel* at the bottom opens the whole panel. Add it to your home screen for a
   one-tap shortcut.

The phone layout shows what the bot is doing, its totals and XP, the activity log and a picture
of the game (one at a time, to go easy on mobile data). **Start** starts the task as it was last
set up on the PC; **Start plan** starts the saved plan. Stop asks first, so a pocket tap can't end
a long run.

To turn it off again: `tailscale serve --bg off` (or `tailscale serve reset`).

## 2. Notifications (ntfy)

1. Install the free **ntfy** app (Play Store / App Store).
2. In the phone layout open **🔔 Phone notifications**. Grindstone has made up a random topic
   name - in the ntfy app tap **+** and subscribe to exactly that topic.
3. Tick **Turn on**, choose what you want to hear about, and **Save**. **Send a test** checks it.
4. Put your Tailscale address (ending in `/m`) under *Open this when a notification is tapped*
   and a notification opens the panel.

You can be told when:

- **the bot stops by itself** - finished, crashed, gave up (not when you press Stop)
- **something needs you** - the game froze, a step was given up, auto login is paused, your
  character keeps dying, or the game window is minimized (the bot waits until it isn't)
- **a skill levels up**
- **every few hours** - a progress summary while it runs

Each kind of problem is sent at most once every 30 minutes. Only the bot's status is sent (what
stopped and why, levels, totals) - never your game login. The topic name works like a password:
anyone who knows it can read the messages, so keep the random one.

## Before you go out

- Settings → System → Power: set the PC never to sleep while plugged in.
- Don't minimize the game window - the bot waits while it is. Behind other windows, or the
  screen switched off, is fine.
