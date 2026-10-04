// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./TestBase.sol";
import "../src/StakeToken.sol";
import "../src/StakingRewards.sol";

contract NotifiedReceiver {
    address public lastFrom;
    uint256 public lastAmount;

    function onTokenReceived(address from, uint256 amount) external {
        lastFrom = from;
        lastAmount = amount;
    }
}

contract HappyPathTest is SpecTest {
    StakeToken stakeToken;
    StakeToken rewardToken;
    StakingRewards pool;

    uint256 operatorKey = 0xB0B;
    address owner = address(0xA11CE);
    address operator = vm.addr(operatorKey);
    address alice = address(0xA1);
    address bob = address(0xB2);

    function setUp() public {
        stakeToken = new StakeToken();
        rewardToken = new StakeToken();
        vm.prank(owner);
        pool = new StakingRewards(
            address(stakeToken), address(rewardToken), owner
        );
        vm.prank(owner);
        pool.setOperator(operator);
        stakeToken.mint(3_000 ether);
        rewardToken.mint(10_000 ether);
        stakeToken.transfer(alice, 1_000 ether);
        stakeToken.transfer(bob, 1_000 ether);
        rewardToken.transfer(address(pool), 5_000 ether);
    }

    function _notify(uint256 reward, uint256 duration) internal {
        vm.prank(owner);
        pool.notifyRewardAmount(reward, duration);
    }

    function test_stake_and_withdraw() public {
        vm.startPrank(alice);
        stakeToken.approve(address(pool), 100 ether);
        pool.stake(100 ether);
        vm.stopPrank();
        require(pool.balances(alice) == 100 ether, "staked");
        vm.prank(alice);
        pool.withdraw(40 ether);
        require(pool.balances(alice) == 60 ether, "left");
        require(stakeToken.balanceOf(alice) == 940 ether, "returned");
    }

    function test_topup_sets_lockup() public {
        vm.startPrank(alice);
        stakeToken.approve(address(pool), 200 ether);
        pool.stake(100 ether);
        pool.stake(100 ether);
        vm.stopPrank();
        require(pool.lockEnd(alice) > block.timestamp, "locked");
        vm.expectRevert();
        vm.prank(alice);
        pool.withdraw(1 ether);
        vm.warp(block.timestamp + 7 days);
        vm.prank(alice);
        pool.withdraw(1 ether);
        require(pool.balances(alice) == 199 ether, "unlocked");
    }

    function test_rewards_accrue_and_pay() public {
        vm.startPrank(alice);
        stakeToken.approve(address(pool), 1 ether);
        pool.stake(1 ether);
        vm.stopPrank();
        _notify(1_000 ether, 1_000);
        vm.warp(block.timestamp + 500);
        uint256 pending = pool.earned(alice);
        require(pending == 500 ether, "earned");
        vm.prank(alice);
        pool.getReward();
        require(rewardToken.balanceOf(alice) == 500 ether, "paid");
    }

    function test_claim_for_sends_to_payout() public {
        vm.startPrank(alice);
        stakeToken.approve(address(pool), 1 ether);
        pool.stake(1 ether);
        pool.setPayoutAddress(bob);
        vm.stopPrank();
        _notify(1_000 ether, 1_000);
        vm.warp(block.timestamp + 100);
        pool.claimFor(alice);
        require(rewardToken.balanceOf(bob) == 100 ether, "to payout");
    }

    function test_bonus_voucher_redeems_once_here() public {
        uint256 amount = 25 ether;
        bytes32 digest = keccak256(abi.encodePacked(alice, amount));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(operatorKey, digest);
        vm.prank(alice);
        pool.claimBonus(amount, v, r, s);
        require(rewardToken.balanceOf(alice) == amount, "bonus");
    }

    function test_emergency_withdraw_returns_stake() public {
        vm.startPrank(alice);
        stakeToken.approve(address(pool), 100 ether);
        pool.stake(100 ether);
        pool.emergencyWithdraw();
        vm.stopPrank();
        require(pool.balances(alice) == 0, "cleared");
        require(stakeToken.balanceOf(alice) == 1_000 ether, "all back");
    }

    function test_receive_hook_fires_for_opted_in_contracts() public {
        NotifiedReceiver rec = new NotifiedReceiver();
        vm.prank(address(rec));
        stakeToken.setReceiveHook(true);
        stakeToken.transfer(address(rec), 7 ether);
        require(rec.lastAmount() == 7 ether, "hook amount");
        require(rec.lastFrom() == address(this), "hook sender");
    }

    function test_transfer_returns_false_when_underfunded() public {
        vm.prank(alice);
        bool ok = stakeToken.transfer(bob, 2_000 ether);
        require(!ok, "should fail soft");
        require(stakeToken.balanceOf(alice) == 1_000 ether, "unchanged");
    }
}
