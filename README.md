# Animal Farm

Animal Farm is a separate FastAPI dashboard game in the Daily Tracker Arcade family. It runs at `http://127.0.0.1:8002` and stores gameplay in `animal-farm.db`.

## Authentication

An active Daily Target Tracker session is accepted automatically using the tracker session signature and user identity. Tracker admin roles inherit Animal Farm admin access. Players who do not use Daily Target Tracker can create a separate game account at `/login`; passwords use salted PBKDF2 hashes.

## Time system

Production and transport use server-side UTC timestamps, so progress continues while the browser is closed. The initial hen cycle is two hours and the bicycle market journey is one hour. Goat, sheep, and cow cycles, feed duration, prices, capacity, and starting economy are configurable from `/admin`.

Feed is purchased from the marketplace and stored in the shared inventory. Each initial feed pack uses `0.1` capacity block, and one matching pack is consumed per animal when a feed cycle begins. An animal group cannot be fed again until its active feed cycle expires. The dashboard displays separate countdowns for feed expiry and the next product cycle.

Animals are stored in purchase batches with independent feed and production timestamps. Newly purchased animals always begin hungry and cannot inherit an older batch's feed or partially completed production cycle. Feeding consumes packs only for hungry animals; already-fed batches keep their original timers.

Inventory, owned animals, transport/deliveries, and the Farmies ledger open as full-screen management panels from the fixed vertical tool rail on the right edge of the farm dashboard. Goods are first loaded from Inventory into the transport cargo bay, where the player can review quantities, remove items, and send the complete load to market. Unwanted inventory can be discarded by quantity with confirmation and an audit entry. Loading is unavailable while transport is travelling, and capacity, stock, ownership, and busy-state rules are enforced by the server.

The Marketplace is divided into Feed, Animals, Inventory, and Transport tabs, with Feed selected by default. Farmers can sell owned livestock from the separate My Animals panel using the admin-configured per-animal sell price. Sales are audited, free the animal's land, and require ready products to be collected first.

Admins can create reusable feed catalog items and new animal species from `/admin`. Each animal records its land requirement, purchase price, animal resale price, product details, product market sale price, storage size, production interval, feed duration, icon, and selected feed. Existing animal feed assignments, prices, and economy settings can also be changed from the economy table.

## Levels, XP, and upgrades

Farmers earn permanent Animal Farm XP from settled market sales and successful permanent-development purchases. Small transactions accumulate toward the configured Farmies-per-XP rates; feed and reversible logistics actions do not award XP. XP sources and adjustments are idempotent and audited. Existing eligible ledger history is backfilled once, and the highest level a farmer reaches is never reduced.

Level 1 unlocks Hen and Goat. Level 2 defaults to 100 XP and unlocks Duck, Goose, the 50-block land expansion, Inventory Level 2 (+10 capacity using 2 land blocks at the default 5:1 ratio), and Bicycle Level 2 (75 capacity and a 45-minute trip). Other animals and larger land expansions remain locked until an admin assigns a level. The admin panel controls level thresholds, animal and land unlocks, XP rates, manual audited XP adjustments, and creation/editing of inventory and transport upgrade levels.

## Service commands

```bash
cd /Users/gt/Developer/animal-farm
./scripts/animal-farm-service start
./scripts/animal-farm-service stop
./scripts/animal-farm-service restart
./scripts/animal-farm-service status
./scripts/animal-farm-service logs
```

The user LaunchAgent is installed as `com.pratik.animal-farm` and requires no administrator privileges.

## Release

This repository is Animal Farm **v1.0.0**, created by Pratik Thombre.
