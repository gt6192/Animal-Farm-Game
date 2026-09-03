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

### v3.0.4

Processing catalogue editing is presented in compact, responsive record cards: save and delete/archive actions stay together, while recipe inputs use a dedicated ingredient-builder panel.

### v3.1.0

Processing buildings are one-time purchases. Each building now has its own paid slot-level path, allowing admins to configure the Farmies cost, player-level requirement, and total processing slots for every upgrade level.

### v3.1.1

The processing workshop uses a per-building slot board. Each idle slot selects and starts exactly one recipe output; active and ready jobs remain in their own slot until collected, with no separate processing-history panel.

### v3.1.2

The Processing admin workspace is grouped into focused sub-tabs for Buildings, Slot levels, Products, Recipes, and Job audit.

### v3.1.3

Fixed Processing admin sub-tab visibility so only the selected panel is displayed.

### v3.1.4

Processing slot recipe choices display their configured ingredient quantities and output, rather than duplicating the recipe title.

### v3.1.5

Inventory upgrade cards show the current inventory land footprint, additional land required for the selected capacity, and resulting total footprint.

### v3.1.6

Land expansion administration supports creating custom packages, editing price and required level, and removing future offers without changing land already owned by farmers.

### v3.1.7

Retired the reserved fixed-farm-area feature. Existing and new farms use no hidden fixed land allocation, returning that space to available land.

### v3.1.8

Restored the visible next slot-level upgrade action inside each eligible Processing building card.

### v3.1.9

Fishery pond cards show their next upgrade throughout the pond lifecycle, explaining required level, added land, and when an active cycle must be finished first.

### v3.2.0

Land expansion offers are individually configurable by player level, block amount, and Farmies price. Each offer can be purchased once per farmer, including offers with the same block amount at different levels. Marketplace animal cards show their assigned feed.

### v3.2.1

Marketplace animal cards use a compact feed badge with intentional spacing, keeping nutrition information readable without crowding the product and purchase details.

### v3.2.2

Land-offer ownership is recorded per unique offer rather than per shared block amount. Legacy purchases are safely reconciled so buying one 50-block offer does not mark every 50-block offer as owned.

### v3.2.3

Administrators can configure the number of feed packs one animal consumes per feed cycle. Feeding calculates the exact pack total for every hungry animal, and unused feeds can be deleted safely after they are unassigned and no farmer has stock remaining.

### v3.2.4

Feed delete actions stay within their matching feed card beside Save, preserving a tidy admin grid.

### v3.2.5

Fishery cards and the seed marketplace show the configured fish sale value. Inventory now totals the current market value of sellable stock, excluding consumable feed. A compact main-page farm dashboard summarizes Farmies, land, livestock, sellable inventory value, fish stock, and transport load.

### v3.2.6

Fixed inventory valuation for existing animal-product rows, restoring the main dashboard for inventories created before the sellable-stock summary.

## v4.0 — Farm Reputation Network (in progress)

Turn surplus stock into a strategic resource through local partners rather than another generic sell button. Farmers can supply local organizations directly from inventory while a transport vehicle or processing slot is busy.

### Partners and orders

- Configurable partners such as a school kitchen, bakery, cheese shop, wool mill, and fish café.
- Each partner has a player-specific reputation level, order history, and optional unlock level.
- Partners publish time-limited, mixed-item orders: for example, eggs plus goat milk for a school kitchen, or fish plus cartons for a café.
- Fulfilling an order deducts only the exact requested inventory items and settles Farmies immediately without requiring transport.
- Local orders pay less than the main market and do not replace transport sales; transport remains the highest immediate sale route and continues to grant sales XP.

### Reputation progression

- Successful orders increase only that partner's reputation.
- Higher reputation unlocks larger orders, better local prices, recurring contracts, and partner-specific benefits.
- Ignoring an expired order may reduce reputation modestly; no stock is ever removed automatically.
- All settlements, reputation changes, expiry handling, and rewards are immutable and idempotent.

### Administration

- Admins can create, edit, enable, archive, and order local partners.
- Admins configure reputation thresholds, order templates, product quantities, Farmies rewards, expiry durations, recurrence, player-level requirements, and reputation effects.
- Admins can review per-user partner reputation, completed orders, and settlement ledger entries, with manual adjustments requiring a reason.

### Player experience

- A dedicated Local Partners panel shows available orders, required stock, completion readiness, reward, expiry, and reputation progress.
- Orders clearly distinguish instant local settlement from vehicle-based market delivery.
- Existing inventory, transport, processing, Farmies ledger, XP, user isolation, and catalog data remain intact.

### Vendor map and delivery riders

- Add a lightweight Farm Map page with a clear map-like layout of local vendors. It is an operational view, not a graphics-heavy game screen.
- Admins can create, edit, enable, archive, and position vendors; configure vendor name, icon, category, player-level requirement, available order templates, and delivery settings.
- Vendors receive completed local-partner orders through delivery riders. Exact order stock is reserved and then deducted only once when a delivery begins; settlement occurs once the delivery reaches its scheduled completion time.
- Delivery riders are a player-owned roster. Rider unlock level, name, icon, delivery capacity, and delivery duration are admin-configurable.
- A player may use only an unlocked and idle rider. Each rider handles one vendor delivery at a time; higher player levels unlock additional riders so several vendor deliveries can run in parallel.
- Each completed rider delivery includes an admin-configured tip. The default v4 interpretation is that this is a delivery cost deducted from the vendor order payout and recorded separately in the Farmies ledger. Admins may set it to zero.
- Admins can configure default and per-vendor delivery durations, delivery tips, and rider capacity. Active deliveries snapshot those economics and timing values, so later catalog edits do not change work already in progress.
- The map shows vendor availability, order readiness, assigned rider, countdown, reward, tip, and resulting net Farmies before the player starts a delivery.

### v4.0.0 — Vendor Map & delivery riders

Implemented the first v4 stage: a lightweight Vendor Map, editable vendor catalog, editable local order catalog, and editable delivery-rider catalog. Riders unlock by player level, have configurable capacity, duration, and per-delivery tip, and can work in parallel when unlocked. Orders reserve stock at departure, settle exactly once after the server-timed journey, and record the net reward in the Farmies ledger. Levels 3–10 are seeded for progression configuration.
