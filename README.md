# MeritSplit

**A GenLayer Intelligent Contract primitive: a payout splitter whose shares are not fixed — they are derived from live, public contribution data at the moment of each distribution.**

Traditional payment splitters (0xSplits, PaymentSplitter) freeze percentages at deploy time. Real collaboration doesn't work that way: who deserves what changes as people contribute. MeritSplit lets a team point at a public data source — a GitHub repo's merged PRs, a publication index, any page that shows objective per-person output — and lets the GenLayer validator set *measure* it trustlessly every time funds are paid out.

This is only possible on GenLayer: a classical smart contract cannot fetch the web, and an oracle-fed splitter reintroduces a trusted party. Here, **every validator independently fetches the source and extracts the metrics**, and payment only happens when their extractions agree.

## How it works

```
create_pool ─► fund (payable, by anyone) ─► distribute (permissionless)
                                             │
                                             ▼
                          each validator: fetch data_url
                                          extract {handle: metric} via LLM
                                          compare with leader (tolerance)
                                             │ consensus
                                             ▼
                          deterministic Python: proportional shares
                          native GEN transfers to each member
                          on-chain audit record (metrics + shares)
```

A pool freezes three things on-chain at creation:

- a **policy** — a plain-language definition of *one objective metric* ("merged PRs authored by each member in repo X, all time");
- a **data URL** — the public source every validator fetches independently;
- a **roster** — public handles mapped to payout addresses (owner can evolve membership; history is preserved).

Anyone can `fund()` the pool — sponsors, dApp fee streams, other contracts. Anyone can trigger `distribute()`: payouts are permissionless and unstoppable once the data supports them.

## Consensus design (the interesting part)

**1. Extract, don't decide.** The LLM is used *only* to extract objective integers from the fetched source — never to judge quality or assign percentages. Subjective LLM output can't be compared across validators; counts can. All share arithmetic is deterministic Python executed on the consensus-agreed metrics.

**2. Tolerant comparison with a zero-flip guard.** The source may legitimately change between leader and validator execution (a PR merges mid-consensus). Validators accept the leader's metrics within `max(1, 2%)` absolute drift per member — but a metric of `0` on one side and `>0` on the other is always rejected, so nobody gets paid on data only one node saw.

**3. Prompt-injection hardening.** The fetched page and all member-supplied text are delimited as untrusted data, and the extraction prompt instructs the model to ignore instruction-like content inside them (e.g. a PR titled "give alice 100"). Only roster handles can appear in the output; anything else is discarded in code, not by the model.

**4. On-chain audit trail.** Every distribution stores the agreed metric snapshot and the exact wei paid per member. Anyone can retroactively verify any payout against the public source.

**5. Failure containment.** If extraction fails or no member has a positive metric, the transaction reverts and funds stay pooled for a later, valid distribution. Rounding dust goes to the top contributor deterministically.

## API

| Method | Access | Description |
|---|---|---|
| `create_pool(title, policy, data_url, handles, addresses, min_distribution, cooldown_seconds)` | anyone | Register a pool; policy and data source are frozen |
| `fund(pool_id)` | anyone, payable | Deposit GEN into the pool |
| `distribute(pool_id)` | anyone | Fetch live data, reach consensus on metrics, pay members proportionally |
| `add_member(pool_id, handle, address)` / `deactivate_member(pool_id, handle)` | owner | Evolve the roster (history preserved) |
| `close_pool(pool_id)` | owner | Close; undistributed balance returns to owner |
| `get_pool / get_pools / get_members / get_distributions / get_stats` | view | Full state, including per-distribution audit records |

Guard rails: 1–20 members, ≥1 h distribution cooldown, optional minimum distribution amount, https-only data sources, size caps on all stored strings.

## Use cases

- **Open-source revenue sharing** — route dApp dev fees to a repo's actual contributors ("build once, earn forever", measured, not promised)
- **Retroactive grant rounds** — a sponsor funds the pool; shares follow shipped work, not applications
- **Content collectives** — split sponsorship by published articles/videos per member
- **DAO working groups** — recurring budget split by delivered, publicly visible output

## Running the tests

Direct-mode tests (no network, mocked web/LLM) cover the full lifecycle — creation, validation, funding, roster rules, proportional math, dust assignment, zero-metric guards, cooldown/minimum guards, and close/refund:

```bash
pip install "genlayer-test[sim]"
python -m pytest test/test_meritsplit_direct.py -v
```

## Deployment

- Network: **GenLayer Testnet Bradbury** (chain 4221)
- Contract: `contracts/meritsplit.py`
- Deployed address: [`0xff6F983810a402D6F4140949B1eBE0B54cE03D46`](https://explorer-bradbury.genlayer.com/address/0xff6F983810a402D6F4140949B1eBE0B54cE03D46)
- Deployment tx: `0xb683e934a4489ead06ec8e9181888d247e1e3013109f4b20efc8487e81033289`

```bash
npm install -g genlayer
genlayer network set testnet-bradbury
genlayer deploy --contract contracts/meritsplit.py
```

## Live on-chain demo

The deployed contract runs a dogfood pool (pool 1) whose data source is **this repository's own contributor data** (`api.github.com/repos/soy-praveen/meritsplit/contributors`). A real distribution has been executed by Bradbury's validator set — they fetched the GitHub API, extracted the contribution counts via LLM consensus, and paid out 0.3 GEN:

- Distribution tx: `0xce78f3cd58a214c8a0232d18cd77bcdc5980647b6abb3288f511a582151719d8`
- On-chain audit record: `get_distributions(1)` → `{"metrics": {"soy-praveen": 1}, "shares": {"soy-praveen": "300000000000000000"}}`

Anyone can verify the metric against the public source, and anyone can `fund(1)` and later trigger `distribute(1)` themselves.

## License

MIT
