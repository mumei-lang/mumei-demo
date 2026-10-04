// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./TestBase.sol";
import "../src/EnglishAuction.sol";

contract HappyPathTest is SpecTest {
    EnglishAuction auction;

    address seller = address(0x5E11);
    address alice = address(0xA1);
    address bob = address(0xB2);
    address carol = address(0xC3);

    function setUp() public {
        auction = new EnglishAuction();
        auction.init(seller, 1 ether, 1 days, 500);
        vm.deal(alice, 20 ether);
        vm.deal(bob, 20 ether);
        vm.deal(carol, 20 ether);
        vm.deal(address(this), 20 ether);
    }

    function _end() internal {
        vm.warp(auction.endTime() + 1 days);
        vm.roll(auction.endBlock() + 1);
    }

    function test_bid_sets_highest() public {
        vm.prank(alice);
        auction.bid{value: 1.5 ether}();
        require(auction.highestBidder() == alice, "highest bidder");
        require(auction.highestBid() == 1.5 ether, "highest bid");
    }

    function test_outbid_refunds_previous() public {
        vm.prank(alice);
        auction.bid{value: 1.5 ether}();
        uint256 before = alice.balance;
        vm.prank(bob);
        auction.bid{value: 2 ether}();
        require(alice.balance == before + 1.5 ether, "refund");
        require(auction.highestBidder() == bob, "new highest");
    }

    function test_min_next_bid_scales_with_increment() public {
        vm.prank(alice);
        auction.bid{value: 2 ether}();
        require(auction.minNextBid() == 2.1 ether, "min next");
    }

    function test_cancel_and_withdraw() public {
        vm.prank(alice);
        auction.bid{value: 1.5 ether}();
        vm.prank(alice);
        auction.cancelBid();
        require(auction.pendingReturns(alice) == 1.5 ether, "pending");
        uint256 before = alice.balance;
        vm.prank(alice);
        auction.withdraw();
        require(alice.balance == before + 1.5 ether, "withdrawn");
    }

    function test_finalize_pays_seller() public {
        vm.prank(alice);
        auction.bid{value: 1.5 ether}();
        vm.prank(bob);
        auction.bid{value: 2 ether}();
        _end();
        uint256 before = seller.balance;
        auction.finalize();
        require(seller.balance == before + 2 ether, "seller paid");
    }

    function test_late_bid_within_grace_accepted() public {
        vm.prank(alice);
        auction.bid{value: 1.5 ether}();
        vm.warp(auction.endTime() + 10 minutes);
        vm.prank(bob);
        auction.bid{value: 2 ether}();
        require(auction.highestBidder() == bob, "late bid landed");
    }

    function test_early_bird_bonus_draw() public {
        vm.prank(alice);
        auction.bid{value: 1.5 ether}();
        vm.prank(bob);
        auction.bid{value: 2 ether}();
        auction.fundBonus{value: 1 ether}();
        _end();
        uint256 total = alice.balance + bob.balance;
        auction.drawEarlyBirdBonus();
        require(auction.bonusPaid(), "drawn");
        require(
            alice.balance + bob.balance == total + 1 ether, "bonus paid"
        );
    }
}
