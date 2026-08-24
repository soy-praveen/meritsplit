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

**2. One canonical result, bound by strict equality.** Every validator reduces its own extraction to a canonical sorted-JSON string of integers, and consensus uses `gl.eq_principle.strict_eq` over that string. Payouts derive solely from those numbers, so byte-equality between validators is equality of the resulting payouts — there is no tolerance window in which two validators could approve different payout outcomes. If the source changes mid-consensus, the transaction fails cleanly, funds stay pooled, and the distribution can simply be retried.

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
- Deployed address: [`0xa00d4d12301972e0f33CDE29a09DEcE4e397b7c4`](https://explorer-bradbury.genlayer.com/address/0xa00d4d12301972e0f33CDE29a09DEcE4e397b7c4)
- Deployment tx: `0x5e46bdd3dd4f54baded6f57af4a4566a8a5f9c1822c8f52817a4bc16f6517c6b`

```bash
npm install -g genlayer
genlayer network set testnet-bradbury
genlayer deploy --contract contracts/meritsplit.py
```

## Live on-chain demo

The deployed contract runs a dogfood pool (pool 1) whose data source is **this repository's own contributor data** (`api.github.com/repos/soy-praveen/meritsplit/contributors`). A real distribution has been executed by Bradbury's validator set — they fetched the GitHub API, extracted the contribution counts via LLM consensus, and paid out 0.3 GEN:

- On-chain audit record: `get_distributions(1)` → `{"metrics": {"soy-praveen": 1}, "shares": {"soy-praveen": "300000000000000000"}}`

Anyone can verify the metric against the public source, and anyone can `fund(1)` and later trigger `distribute(1)` themselves.

## License

MIT
