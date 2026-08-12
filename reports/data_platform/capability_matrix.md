# MLB data capability matrix

| Capability | Existing Statcast | MLB Stats API | Retrosplits | Vegas 2012–2021 | Andy workflow | Platform decision |
|---|---|---|---|---|---|---|
| Canonical MLB `game_pk` | Yes, modern games | Authoritative | Retrosheet game key | No | Odds API event id | MLB id when available; immutable source alias otherwise |
| Pitch-level outcomes / quality | Yes | Limited | Event-derived aggregates | No | No | Statcast remains authoritative |
| Historical player game lines | Derivable for Statcast era | Game/boxscore endpoints | Yes (`evt`, `box`, `ded`) | No | Scores only | Retrosplits backfill; retain source quality |
| Team game history | Derivable | Yes | Yes | Scores duplicated in enriched file | Yes | Retrosplits selected; no duplicate score ingestion |
| Suspended-game appearances | Partial | Status/resume metadata | `game.date` and `appear.date` | No | No | Retrosplits preserves both dates |
| Doubleheaders | `game_pk` | `doubleHeader`/game number | `game.number` | `gameNumber` | Event id | Canonical normalized number with exact alias |
| Venue | Yes | Authoritative id/name | `site.key` | Venue name in enriched file | Commence metadata | MLB id preferred; source venue retained |
| Starting lineups | Statcast actual participants | Official/live lineup | Postgame participants only | No | No | Never treat postgame participants as pregame lineup |
| Rolling hitter/pitcher form | Existing point-in-time store | Source for live queries | Historical inputs | No | No | Statcast modern; Retrosplits historical backfill |
| Bullpen history/fatigue | Existing derived tables | Live roster/boxscore | Pitching game lines | No | No | Shifted completed-game data only |
| Closing moneyline/total | No | No | No | Yes | Historical Odds API | Vegas fills 2012–2021 target gap |
| Market snapshots / movement | Existing live snapshots | No | No | Closing only | Yes | Existing live service + generic historical JSON importer |
| Licensing/provenance | MLB/Statcast terms | MLB terms | ODbL/Retrosheet notice | Dataset-specific/Retrosheet notice | Third-party API terms | Every run stores source hash/version |

Retrosplits source-selection policy is `evt > box > ded`; alternatives remain stored and are never silently merged. Vegas supplies closing observations only, so it cannot support within-game line movement. Andy's repository contributes a workflow pattern, not an additional historical dataset; the platform implements a Python Odds API v4 JSON importer without copying the R code.
