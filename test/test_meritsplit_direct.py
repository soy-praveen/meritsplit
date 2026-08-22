"""Direct-mode tests for MeritSplit (no network, mocked web/LLM).

Run from the meritsplit project root:
    pytest test/test_meritsplit_direct.py -v
"""

import json

GEN = 10**18
SDK = "v0.2.16"

ALICE = "0x" + "11" * 20
BOB = "0x" + "22" * 20
CARA = "0x" + "33" * 20

POLICY = (
    "Count the number of merged pull requests authored by each roster member "
    "in the repository shown by the data source, all time."
)
DATA_URL = "https://api.github.com/repos/acme/widget/pulls?state=closed"


def _metrics_response(metrics):
    return json.dumps({"metrics": metrics})


def _create(contract, handles=None, addresses=None, cooldown=3600, min_dist=0):
    return contract.create_pool(
        "Widget core team",
        POLICY,
        DATA_URL,
        handles or ["alice", "bob", "cara"],
        addresses or [ALICE, BOB, CARA],
        min_dist,
        cooldown,
    )


def test_create_and_views(direct_vm, direct_deploy):
    contract = direct_deploy("contracts/meritsplit.py", sdk_version=SDK)
    pool_id = _create(contract)
    assert pool_id == 1

    p = contract.get_pool(1)
    assert p["status"] == "ACTIVE"
    assert p["member_count"] == 3
    assert p["balance"] == 0
    assert p["distribution_count"] == 0
    assert contract.get_pools()[0]["id"] == 1

    members = contract.get_members(1)
    assert [m["handle"] for m in members] == ["alice", "bob", "cara"]
    assert all(m["active"] for m in members)


def test_create_validation(direct_vm, direct_deploy):
    contract = direct_deploy("contracts/meritsplit.py", sdk_version=SDK)

    with direct_vm.expect_revert("policy must be"):
        contract.create_pool("t", "short", DATA_URL, ["a"], [ALICE], 0, 3600)
    with direct_vm.expect_revert("must be https"):
        contract.create_pool("t", POLICY, "http://x.com/d", ["a"], [ALICE], 0, 3600)
    with direct_vm.expect_revert("cooldown below 1 hour"):
        contract.create_pool("t", POLICY, DATA_URL, ["a"], [ALICE], 0, 60)
    with direct_vm.expect_revert("duplicate handle"):
        contract.create_pool(
            "t", POLICY, DATA_URL, ["a", "A"], [ALICE, BOB], 0, 3600
        )
    with direct_vm.expect_revert("handles/addresses mismatch"):
        contract.create_pool("t", POLICY, DATA_URL, ["a", "b"], [ALICE], 0, 3600)


def test_fund_and_roster(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy("contracts/meritsplit.py", sdk_version=SDK)
    direct_vm.sender = direct_alice
    _create(contract)

    with direct_vm.expect_revert("send some GEN"):
        contract.fund(1)
    direct_vm.value = 5 * GEN
    contract.fund(1)
    direct_vm.value = 0
    assert contract.get_pool(1)["balance"] == 5 * GEN

    # Roster is owner-gated.
    direct_vm.sender = direct_bob
    with direct_vm.expect_revert("only pool owner"):
        contract.add_member(1, "dan", "0x" + "44" * 20)

    direct_vm.sender = direct_alice
    contract.add_member(1, "dan", "0x" + "44" * 20)
    with direct_vm.expect_revert("handle already exists"):
        contract.add_member(1, "DAN", "0x" + "55" * 20)
    contract.deactivate_member(1, "dan")
    assert contract.get_pool(1)["member_count"] == 3
    with direct_vm.expect_revert("active member with that handle not found"):
        contract.deactivate_member(1, "dan")


def test_distribute_proportional(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/meritsplit.py", sdk_version=SDK)
    direct_vm.sender = direct_alice
    _create(contract)
    direct_vm.value = 10 * GEN
    contract.fund(1)
    direct_vm.value = 0

    direct_vm.mock_web(r".*api\.github\.com.*", {"status": 200, "body": "[pr data]"})
    direct_vm.mock_llm(
        r".*data extraction engine.*",
        _metrics_response({"alice": 6, "bob": 3, "cara": 1}),
    )

    shares = json.loads(contract.distribute(1))
    assert shares["alice"] == 6 * GEN
    assert shares["bob"] == 3 * GEN
    assert shares["cara"] == 1 * GEN

    p = contract.get_pool(1)
    assert p["balance"] == 0
    assert p["total_distributed"] == 10 * GEN

    history = contract.get_distributions(1)
    assert len(history) == 1
    assert history[0]["metrics"] == {"alice": 6, "bob": 3, "cara": 1}
    assert history[0]["amount"] == 10 * GEN

    # Immediately distributing again: no balance, and cooldown not elapsed.
    with direct_vm.expect_revert("pool has no balance"):
        contract.distribute(1)


def test_distribute_dust_goes_to_top(direct_vm, direct_deploy):
    contract = direct_deploy("contracts/meritsplit.py", sdk_version=SDK)
    _create(contract)
    direct_vm.value = 10
    contract.fund(1)
    direct_vm.value = 0

    direct_vm.mock_web(r".*", {"status": 200, "body": "x"})
    direct_vm.mock_llm(
        r".*data extraction engine.*",
        _metrics_response({"alice": 1, "bob": 1, "cara": 1}),
    )
    shares = json.loads(contract.distribute(1))
    # 10 wei / 3 = 3 each with 1 wei dust to the top contributor (alice on tie).
    assert shares == {"alice": 4, "bob": 3, "cara": 3}
    assert sum(shares.values()) == 10


def test_distribute_zero_metric_member_unpaid(direct_vm, direct_deploy):
    contract = direct_deploy("contracts/meritsplit.py", sdk_version=SDK)
    _create(contract)
    direct_vm.value = 4 * GEN
    contract.fund(1)
    direct_vm.value = 0

    direct_vm.mock_web(r".*", {"status": 200, "body": "x"})
    direct_vm.mock_llm(
        r".*data extraction engine.*",
        _metrics_response({"alice": 3, "bob": 1, "cara": 0}),
    )
    shares = json.loads(contract.distribute(1))
    assert shares["cara"] == 0
    assert shares["alice"] == 3 * GEN


def test_distribute_all_zero_reverts(direct_vm, direct_deploy):
    contract = direct_deploy("contracts/meritsplit.py", sdk_version=SDK)
    _create(contract)
    direct_vm.value = GEN
    contract.fund(1)
    direct_vm.value = 0

    direct_vm.mock_web(r".*", {"status": 200, "body": "x"})
    direct_vm.mock_llm(
        r".*data extraction engine.*",
        _metrics_response({"alice": 0, "bob": 0, "cara": 0}),
    )
    with direct_vm.expect_revert("no member has a positive metric"):
        contract.distribute(1)
    # Funds stay in the pool for a later, valid distribution.
    assert contract.get_pool(1)["balance"] == GEN


def test_min_distribution_guard(direct_vm, direct_deploy):
    contract = direct_deploy("contracts/meritsplit.py", sdk_version=SDK)
    _create(contract, min_dist=5 * GEN)
    direct_vm.value = GEN
    contract.fund(1)
    direct_vm.value = 0
    with direct_vm.expect_revert("balance below min distribution"):
        contract.distribute(1)


def test_close_pool_refunds_owner(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy("contracts/meritsplit.py", sdk_version=SDK)
    direct_vm.sender = direct_alice
    _create(contract)
    direct_vm.value = 2 * GEN
    contract.fund(1)
    direct_vm.value = 0

    direct_vm.sender = direct_bob
    with direct_vm.expect_revert("only pool owner"):
        contract.close_pool(1)

    direct_vm.sender = direct_alice
    contract.close_pool(1)
    p = contract.get_pool(1)
    assert p["status"] == "CLOSED"
    assert p["balance"] == 0
    with direct_vm.expect_revert("pool is closed"):
        contract.fund(1)
