// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./TestBase.sol";
import "../src/VaultToken.sol";
import "../src/RewardVault.sol";

contract HappyPathTest is SpecTest {
    VaultToken token;
    RewardVault vault;

    address owner = address(0xA11CE);
    address alice = address(0xA1);
    address bob = address(0xB2);
    address feeSink = address(0xFEE1);

    function setUp() public {
        vm.prank(owner);
        token = new VaultToken();
        vm.prank(owner);
        vault = new RewardVault();
        vm.deal(alice, 100 ether);
        vm.deal(bob, 100 ether);
        vm.deal(owner, 200 ether);
        vm.deal(address(this), 100 ether);
    }

    function test_deposit_mints_shares_one_to_one() public {
        vm.prank(alice);
        vault.deposit{value: 10 ether}();
        require(vault.sharesOf(alice) == 10 ether, "shares");
        require(vault.totalShares() == 10 ether, "total shares");
        require(vault.totalAssets() == 10 ether, "assets");
    }

    function test_share_price_after_first_deposit() public {
        vm.prank(alice);
        vault.deposit{value: 4 ether}();
        require(vault.sharePrice() == 1e18, "price");
    }

    function test_withdraw_returns_assets() public {
        vm.prank(alice);
        vault.deposit{value: 10 ether}();
        uint256 before = alice.balance;
        vm.prank(alice);
        vault.withdraw(4 ether);
        require(alice.balance - before == 4 ether, "payout");
        require(vault.sharesOf(alice) == 6 ether, "shares left");
    }

    function test_withdraw_fee_goes_to_recipient() public {
        vm.prank(owner, owner);
        vault.setWithdrawFeeBps(200);
        vm.prank(owner);
        vault.setFeeRecipient(feeSink);
        vm.prank(alice);
        vault.deposit{value: 10 ether}();
        vm.prank(alice);
        vault.withdraw(10 ether);
        require(feeSink.balance == 0.2 ether, "fee paid");
        require(alice.balance == 99.8 ether, "net payout");
    }

    function test_second_depositor_gets_pro_rata_shares() public {
        vm.prank(alice);
        vault.deposit{value: 10 ether}();
        vm.deal(address(this), 10 ether);
        (bool ok, ) = address(vault).call{value: 10 ether}("");
        require(ok, "topup");
        vm.prank(bob);
        vault.deposit{value: 10 ether}();
        // the fresh deposit already sits in totalAssets, so bob mints
        // 10e18 * 10e18 / 30e18 shares
        require(
            vault.sharesOf(bob) == 3333333333333333333,
            "pro rata shares"
        );
    }

    function test_rewards_distributed_and_claimed() public {
        vm.prank(alice);
        vault.deposit{value: 10 ether}();
        vm.prank(bob);
        vault.deposit{value: 10 ether}();
        vm.prank(owner);
        vault.distributeRewards{value: 40 ether}();
        require(vault.rewards(alice) == 20 ether, "alice reward");
        // bob only holds half the shares alice does
        require(vault.rewards(bob) == 10 ether, "bob reward");
        uint256 before = alice.balance;
        vm.prank(alice);
        vault.claimRewards();
        require(alice.balance - before == 20 ether, "claimed");
    }

    function test_pause_blocks_deposits() public {
        vm.prank(owner);
        vault.pause();
        vm.prank(alice);
        vm.expectRevert();
        vault.deposit{value: 1 ether}();
        vm.prank(owner);
        vault.unpause();
        vm.prank(alice);
        vault.deposit{value: 1 ether}();
        require(vault.sharesOf(alice) == 1 ether, "resumed");
    }

    function test_token_transfer_and_allowance() public {
        vm.prank(owner);
        token.mint(alice, 100 ether);
        vm.prank(alice);
        token.transfer(bob, 40 ether);
        require(token.balanceOf(bob) == 40 ether, "transfer");
        vm.prank(alice);
        token.approve(bob, 20 ether);
        vm.prank(bob);
        token.transferFrom(alice, bob, 20 ether);
        require(token.balanceOf(bob) == 60 ether, "transferFrom");
        require(token.allowance(alice, bob) == 0, "allowance spent");
    }
}
