# Kite subscription permissions — public written check, 2026-10-16

**Personal historical backtesting is supported in principle. Permanent archival permission is not established.** This corrects any reading of the earlier source-use hold as a blanket prohibition of personal historical backtests. Root checked the primary pages afresh; an independent reviewer checked the distinction. No account-specific agreement, receipt terms or private correspondence was inspected.

| Written source | Supported conclusion |
|---|---|
| [Kite staff, May 2025](https://kite.trade/forum/discussion/15036/app-with-access-to-historical-data-only) | Historical data is provided for users' personal backtesting. |
| [Kite staff, 9 October 2026, section 5](https://kite.trade/forum/discussion/16304/written-clarification-for-self-built-kite-connect-trading-system) | Personal analysis is permitted; permanent storage and paper trading using live market data are restricted. Do not extend that live-paper restriction into a blanket historical-backtest ban. |
| [API terms section 4(b)](https://kite.trade/terms/) | Database/permanent-copy restrictions apply unless expressly permitted by Zerodha or applicable law. Payment for access alone does not document an exception. |
| [Direct retention question, 7 October 2026](https://kite.trade/forum/discussion/16295/clarification-on-historical-nse-equity-data-retention-and-personal-quantitative-research) | Staff referred the question to email without providing substantive storage, post-subscription retention or research-database permission. |

No retention duration, temporary-cache policy or permission after subscription cancellation can be inferred from these replies. API terms section 13 gives actual individual agreements and product-specific terms precedence; no such account-specific exception has been verified here. Nothing was sent to a provider.

## Next engineering task

Build and test the already reviewed daily descriptive pilot runner using invented fixtures and the existing simulator/ledger barriers. Its fixed design covers seven SignalSimulator cards and a required 257-session source interval, with no benchmark alpha or strategy promotion. See the [reviewed plan](../plans/2026-10-16-daily-descriptive-pilot.md). This engineering task can proceed without claiming actual input admission; the previous decision to defer invented-fixture work was sequencing, not a permission requirement for writing software.

Before an actual run, qualify the chosen real-data bundle and establish the applicable source-use/retention arrangement. The Kite M15 route additionally needs missing histories and independently justified action/rounding reconciliation. NSE website data has its own separate terms; Kite's personal-backtesting statement does not clear that source automatically. `DATA_QUALIFIED=false`; actual-study `RUN_AUTHORIZED=false`. Provider questions remain UNSENT; no new acquisition, trial or runtime change occurred in this permission check.
