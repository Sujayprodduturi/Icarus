# Daily pilot source-use check — 2026-10-17

The private Kite subscription confirmation was inspected read-only. It confirms the subscription for the historical-data app and links to the developer dashboard; it contains no additional historical-data retention licence or simulation permission. A narrowly scoped mailbox search found no separate Kite Connect permission/retention correspondence. This is not an exhaustive account-contract audit. No private email body, address, payment identifier or credential is included here, and no message was sent.

The public sources were also checked afresh:

- [Kite API terms, sections 4(b) and 13](https://kite.trade/terms/): database/permanent-copy restrictions and precedence of applicable individual/product agreements remain relevant. The receipt supplies no verified exception.
- [Kite staff clarification, section 5](https://kite.trade/forum/discussion/16304/written-clarification-for-self-built-kite-connect-trading-system): personal analysis is supported; permanent storage and live-data paper trading remain restricted. This is not a blanket prohibition of historical backtesting and supplies no cache-retention duration.
- [NSE website terms, Use 8–9](https://www.nseindia.com/static/nse-terms-of-use): website-data simulation and automated-collection restrictions remain present. Kite subscription terms do not clear a separate NSE website source.

The present daily pilot uses saved NSE daily archives for its proposed inputs. Its applicable source-use permission therefore remains unresolved. Technical source QA may proceed under the operator's bounded offline authorization; successful file validation cannot set `source_use_authorized=true`. No strategy evaluation, actual-ledger activation, purchase, provider contact or retention-policy change is authorized by this check. Provider questions remain **UNSENT**.

## Subsequent operator disposition — 2026-10-19

The original findings above remain the record of the provider evidence. The operator has since explicitly instructed personal offline use of the NSE archive, with Kite subscription data as a fallback. D62 and the [dated disposition](2026-10-19-source-use-disposition.md) resolve the operator-side hold for confined local input publication and qualification review. They do not establish provider permission or change the recorded terms. In the bounded final qualification, `source_use_authorized` denotes this operator authority, supported by the separate disposition evidence; it must not be described as a provider licence. Actual strategy evaluation and ledger activation retain their separate gate. Provider questions remain **UNSENT**.
