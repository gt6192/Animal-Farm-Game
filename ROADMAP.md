# Animal Farm Roadmap

## v1.1 — Admin workspace redesign (released)

Turn the current long admin page into a focused administration workspace with a persistent vertical menu. Only the selected logical section is visible at a time, and the selected section is retained across saves and page reloads.

Planned workspaces:

- Overview: player, animal, feed, and upgrade catalog totals.
- Game settings: starting economy and global capacity rules.
- Animals: species creation, purchase/resale prices, products, cycles, feed assignment, land, and unlock levels.
- Feed: feed creation, icons, pricing, storage sizes, and assignments.
- Land: expansion prices and player-level requirements.
- Levels & XP: level thresholds, XP rates, manual adjustments, and history.
- Upgrades: inventory and transport level catalogs.
- Players: accounts, balances, XP, and levels.

The desktop experience uses a sticky vertical sidebar. Smaller screens use a compact horizontally scrollable tab rail. Admin authorization and all existing server-side validation remain unchanged.

## v2.0 — Fishery unit (completed)

Add a catalog-driven fishery system that shares the farm's land, Farmies, inventory, transport, player levels, XP, and ledgers.

### Pond catalog

Admins can create any number of pond levels and configure:

- Pond level, name, icon, and enabled state.
- Required player level.
- Purchase or upgrade price.
- Total land occupied.
- Fish-seed sack capacity.
- Fish produced per sack.
- Growth duration.
- Produced fish species.

Pond upgrades are sequential. Existing ponds remain usable after catalog or level changes, and disabled levels cannot be newly purchased.

### Fish and seed catalogs

Fish species define their icon, inventory size, market sale price, and enabled state. Fish-seed products define their sack price, storage size, and the fish species they stock. Seed purchases are consumables and do not grant development XP.

### Player ponds

Farmers may own multiple independently named ponds, subject to configurable player-level limits. Each pond tracks its catalog level, occupied land, stocked sacks, active cycle timestamps, ready fish, lifetime harvest, and upgrade history.

Default example values, editable by admins:

| Pond | Player level | Land | Sack limit | Output | Growth |
| --- | ---: | ---: | ---: | ---: | ---: |
| Level 1 | Admin assigned | 20 blocks | 1 | 100 fish | 24 hours |
| Level 2 | Admin assigned | 40 blocks | 2 | 200 fish | 24 hours |

### Production rules

- A pond cannot be restocked during an active or unharvested cycle.
- Seed sacks are deducted only after a valid stocking transaction succeeds.
- Growth continues from server-side UTC timestamps while the player is offline.
- Mature fish remain safely in the pond when inventory is full.
- Harvesting is idempotent and occurs exactly once.
- Pond upgrades are blocked during active or unharvested cycles.
- Fish sales earn Farmies and sales XP only after transport settlement.
- Pond construction and upgrades may earn development XP; seed sacks do not.
- Catalog changes affect future cycles and never rewrite active-cycle economics.

### v2.0 administration

Add a Fishery workspace to the v1.1 admin sidebar for pond levels, fish species, seed products, player pond limits, user ponds, cycle history, and fishery economy/XP settings.

### Completion status

Completed for v2.0. Pond limits are enforced by player level, fishery XP eligibility is independently configurable, and administrators can inspect user ponds and recent production cycles. Catalog identifiers remain stable during edits, and active cycles retain their original output and timing snapshots.

## v3.0 — Processing & Admin workspace (released)

The administration console uses a persistent vertical workspace menu on desktop and a compact horizontal tab rail on smaller screens. It separates game settings, animals, feed, land, progression, upgrades, fishery, processing, and player data.

Processing adds configurable buildings, processed products, recipes, inputs, durations, fees, slots, and player-level requirements. Farmers purchase buildings using Farmies and free land, begin server-timed jobs using inventory inputs, collect completed output once, then sell it using existing inventory and transport systems. Jobs preserve their input and output snapshot while running; processing itself grants no XP, while building purchases and settled sales use the established development and sales XP ledger rules.

### v3.0.1

The Processing recipe editor uses a dynamic ingredient builder with product dropdowns, quantities, and add/remove rows. This removes manual product-key entry and supports mixed recipes safely.

### v3.0.2

Animal catalog editing includes product display names and icons, while preserving each stable product key for existing inventory and delivery records.

### v3.0.3

Processing buildings, output products, and recipes are all editable. Unused catalog entries may be deleted; records referenced by owned buildings, jobs, recipes, or inventory are safely archived by disabling them so player data and audit history remain valid.
