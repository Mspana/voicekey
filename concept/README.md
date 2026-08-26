# NYAC member app concept — the Goldilocks pitch

Three fully interactive prototypes for pitching a modern replacement for the New
York Athletic Club member app. The pitch: "I haven't made you one app — I've made
three. One is a little too casual, one a little too fancy, and one is just right."

- `nyac-styles.html` — **the pitch hub**: all three side by side, each linking to
  its interactive app.
- `roll-of-honor.html` — **I · The Roll of Honor** (heritage editorial) — *the
  just-right one*, and the flagship. Libre Caslon + Public Sans; ivory, crimson,
  gilt; Day/Night mode.
- `field-house.html` — **II · The Field House** (modern athletic) — *the too-casual
  foil*. Barlow Semi Condensed; committed dark scoreboard; CH/TI tags.
- `grand-hall.html` — **III · The Grand Hall** (Deco hospitality) — *the too-fancy
  foil and likeliest runner-up*. Cinzel + Jost; concierge voice; Day/Candlelight.
- `nyac-app.html` — the original first-pass prototype (superseded, kept for record).

All three apps share the same instant engine — table reservations, one-tap event
RSVPs, bookings with modify/cancel, statements, menus, and club info — so the
board compares character, not capability. Everything runs client-side on sample
data; every tap is instant.

## Why redesign

Today's app is a thin shell that re-fetches server-rendered pages on every screen,
so it feels slow (multi-second waits) and dated. Members really use it for two jobs:

1. **Reserving** — dining tables and club events.
2. **Knowing** — hours, menus, facilities, statements, Travers Island.

The concept rebuilds around those two jobs.

## Design priorities (from the brief)

1. **Ease of use** — large type, plain labels, generous tap targets, one obvious
   action per screen. Built for the Club's older members first.
2. **Distinguished, not dated** — the engraved crest, an old-style serif (Fraunces),
   aged-gilt hairlines, marble grounds. Institutional but modern.
3. **Instant** — screens are prefetched/cached; no five-second page fetches.
4. **Palette** — crimson `#9E1B32` + white, aged gold `#B08B4F` as accent, and
   pool-blue `#5E97AE` reserved for Travers Island so campus reads at a glance.

Type: **Fraunces** (display serif) + **Libre Franklin** (UI). Light and dark themes.

## What's clickable

- **Reserve a table** — venue → date/time/party → confirm → lands in Bookings.
- **Events** — one-tap RSVP that adds to Bookings (seeded from the current app's calendar).
- **Bookings** — modify / cancel.
- **Club** — hours, menus, facilities, Travers Island, shuttle, reciprocal clubs, statements.
- Light/dark toggle in the header.

## On the data behind it

The current NYAC app is built on **Sibisoft's** platform (app id
`com.sibisoft.newyorkathleticclub`), which is the same **Northstar Club Management
Software** that runs the club website on `clubhouseonline-e3.net` — now part of the
Clubessential Holdings family. It is a **private, undocumented vendor API**, not an
open one, but there is a real network layer underneath.

Three ways to feed live data into a new front-end, best to worst for a pitch:

1. **Sanctioned integration** — an official Northstar / Clubessential API or data
   feed, arranged with the vendor. The right long-term path; needs the Club's buy-in.
2. **Permissioned personal sync** — a member logs in with their own credentials and
   the app mirrors their own data. Works, but likely runs against the app/vendor
   terms of service and is fragile if the vendor changes things.
3. **HTML scraping** of the authenticated web app — last resort, brittle.

For the pitch itself, none of that is needed: the prototype uses sample data so the
conversation stays about the experience. The data layer is deliberately swappable.

## Not affiliated

Independent concept using a stylized crest and sample data. Not the official NYAC
app; not affiliated with or endorsed by the Club or its vendors.
