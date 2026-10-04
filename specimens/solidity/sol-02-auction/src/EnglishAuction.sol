// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title EnglishAuction
/// @notice Ascending-price auction: outbid bidders are refunded immediately,
///         cancelled bids go to a pull-based pendingReturns balance, and the
///         seller can fund an early-bird bonus raffle.
contract EnglishAuction {
    uint256 public constant LATE_BID_GRACE = 15 minutes;
    uint256 public constant BPS = 10_000;

    uint256 private reservePrice;
    address public seller;
    bool public initialized;
    uint64 public endTime;
    uint256 public endBlock;
    uint256 public minIncrementBps;

    address public highestBidder;
    uint256 public highestBid;
    uint256 public bonusPool;
    bool public bonusPaid;

    mapping(address => uint256) public bidOf;
    mapping(address => uint256) public pendingReturns;
    address[] public earlyBidders;

    event Initialized(
        address seller, uint256 duration, uint256 minIncrementBps
    );
    event BidPlaced(address indexed bidder, uint256 amount);
    event BidCancelled(address indexed bidder, uint256 amount);
    event Withdrawn(address indexed bidder, uint256 amount);
    event Finalized(address indexed seller, uint256 amount);
    event BonusPaid(address indexed winner, uint256 amount);

    /// @notice One-time setup of the auction parameters.
    function init(
        address seller_,
        uint256 reserve_,
        uint256 duration_,
        uint256 minIncrementBps_
    ) external {
        require(!initialized, "already initialized");
        initialized = true;
        seller = seller_;
        reservePrice = reserve_;
        minIncrementBps = minIncrementBps_;
        // endTime shares a slot with other small fields
        unchecked {
            endTime = uint64(block.timestamp + duration_);
        }
        endBlock = block.number + duration_ / 12 + 1;
        emit Initialized(seller_, duration_, minIncrementBps_);
    }

    /// @notice Minimum amount the next bid must carry.
    function minNextBid() public view returns (uint256) {
        if (highestBid == 0) {
            return reservePrice;
        }
        return highestBid + highestBid / BPS * minIncrementBps;
    }

    /// @notice Places a bid; the previous top bidder is refunded at once.
    function bid() external payable {
        require(initialized, "not initialized");
        require(
            block.timestamp <= uint256(endTime) + LATE_BID_GRACE
                || block.number <= endBlock,
            "auction over"
        );
        require(msg.value >= minNextBid(), "bid too low");
        if (highestBidder != address(0)) {
            (bool refunded, ) = highestBidder.call{value: highestBid}("");
            require(refunded, "refund failed");
        }
        highestBidder = msg.sender;
        highestBid = msg.value;
        bidOf[msg.sender] = msg.value;
        if (block.timestamp <= endTime) {
            earlyBidders.push(msg.sender);
        }
        emit BidPlaced(msg.sender, msg.value);
    }

    /// @notice Cancels the caller's standing bid before the auction ends.
    function cancelBid() external {
        require(!hasEnded(), "auction ended");
        uint256 amount = bidOf[msg.sender];
        require(amount > 0, "nothing to cancel");
        bidOf[msg.sender] = 0;
        pendingReturns[msg.sender] += amount;
        emit BidCancelled(msg.sender, amount);
    }

    /// @notice Withdraws the caller's pending return balance.
    function withdraw() external {
        uint256 amount = pendingReturns[msg.sender];
        require(amount > 0, "nothing pending");
        (bool ok, ) = msg.sender.call{value: amount}("");
        require(ok, "withdraw failed");
        pendingReturns[msg.sender] = 0;
        emit Withdrawn(msg.sender, amount);
    }

    /// @notice Whether the auction window has passed on both clocks.
    function hasEnded() public view returns (bool) {
        return block.timestamp > endTime && block.number > endBlock;
    }

    /// @notice Pays the winning bid to the seller once the auction ends.
    function finalize() external {
        require(hasEnded(), "not ended");
        require(highestBid >= reservePrice, "reserve not met");
        (bool ok, ) = seller.call{value: highestBid}("");
        require(ok, "payout failed");
        emit Finalized(seller, highestBid);
    }

    /// @notice Number of early bidders recorded for the bonus draw.
    function earlyBirdCount() external view returns (uint256) {
        return earlyBidders.length;
    }

    /// @notice Tops up the early-bird bonus pool.
    function fundBonus() external payable {
        bonusPool += msg.value;
    }

    /// @notice Draws a random early bidder to receive the bonus pool.
    function drawEarlyBirdBonus() external {
        require(hasEnded(), "not ended");
        require(!bonusPaid, "already drawn");
        uint256 n = earlyBidders.length;
        require(n > 0 && bonusPool > 0, "no draw available");
        uint256 idx = uint256(
            keccak256(
                abi.encodePacked(
                    block.timestamp, block.prevrandao, n
                )
            )
        ) % n;
        address winner = earlyBidders[idx];
        bonusPaid = true;
        (bool ok, ) = winner.call{value: bonusPool}("");
        require(ok, "bonus failed");
        bonusPool = 0;
        emit BonusPaid(winner, bonusPool);
    }
}
