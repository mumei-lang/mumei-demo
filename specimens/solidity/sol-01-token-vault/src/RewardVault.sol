// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title RewardVault
/// @notice ETH vault issuing shares pro-rata, charging a withdraw fee and
///         distributing periodic ETH rewards to share holders.
contract RewardVault {
    struct Position {
        uint128 shares; // packed into one slot
        uint64 lastDepositAt; // packed into one slot
    }

    uint256 public constant MAX_FEE_BPS = 1_000;
    uint256 public constant BPS = 10_000;

    address public owner;
    address public feeRecipient;
    uint256 public withdrawFeeBps;
    bool public paused;

    uint256 public totalShares;
    uint256 public rewardsOwed;
    mapping(address => Position) public positions;
    mapping(address => uint256) public rewards;
    address[] public holders;

    event Deposit(address indexed user, uint256 assets, uint256 shares);
    event Withdraw(
        address indexed user, uint256 shares, uint256 assets, uint256 fee
    );
    event RewardsDistributed(uint256 amount);
    event RewardsClaimed(address indexed user, uint256 amount);

    modifier onlyOwner() {
        require(msg.sender == owner, "not owner");
        _;
    }

    modifier whenActive() {
        require(!paused, "paused");
        _;
    }

    constructor() {
        owner = msg.sender;
        feeRecipient = msg.sender;
    }

    /// @notice Accepts stray ETH top-ups that raise the share price.
    receive() external payable {}

    /// @notice Deposits ETH and mints shares at the current price.
    function deposit() external payable whenActive {
        require(msg.value > 0, "zero deposit");
        uint256 shares = _sharesFor(msg.value);
        Position storage pos = positions[msg.sender];
        pos.shares += uint128(shares);
        pos.lastDepositAt = uint64(block.timestamp);
        totalShares += shares;
        holders.push(msg.sender);
        emit Deposit(msg.sender, msg.value, shares);
    }

    /// @notice Shares that a deposit of `assets` wei would mint.
    function previewDeposit(uint256 assets) external view returns (uint256) {
        return _sharesFor(assets);
    }

    /// @notice ETH backing shares, excluding credited rewards.
    function totalAssets() public view returns (uint256) {
        return address(this).balance - rewardsOwed;
    }

    /// @notice Price of one share in wei.
    function sharePrice() external view returns (uint256) {
        return totalAssets() * 1e18 / totalShares;
    }

    /// @notice Shares recorded for `user`.
    function sharesOf(address user) external view returns (uint256) {
        return positions[user].shares;
    }

    /// @notice Burns `shares` and pays out the corresponding ETH, minus fee.
    function withdraw(uint256 shares) external whenActive {
        Position storage pos = positions[msg.sender];
        require(pos.shares >= shares, "not enough shares");
        uint256 assets = shares * totalAssets() / totalShares;
        uint256 fee = assets * withdrawFeeBps / BPS;
        uint256 net = assets - fee;
        // settle any accrued rewards together with the principal
        uint256 pending = rewards[msg.sender];
        _payFee(fee);
        _payout(msg.sender, net);
        if (pending > 0) {
            _payout(msg.sender, pending);
        }
        rewards[msg.sender] = 0;
        rewardsOwed -= pending;
        pos.shares -= uint128(shares);
        totalShares -= shares;
        emit Withdraw(msg.sender, shares, assets, fee);
    }

    /// @notice Credits every recorded holder with `perShare * shares` wei.
    function distributeRewards() external payable onlyOwner {
        uint256 perShare = msg.value / totalShares;
        uint256 credited;
        for (uint256 i = 0; i < holders.length; i++) {
            address h = holders[i];
            uint256 c = perShare * positions[h].shares;
            rewards[h] += c;
            credited += c;
        }
        rewardsOwed += credited;
        emit RewardsDistributed(msg.value);
    }

    /// @notice Pays out the caller's accrued rewards.
    function claimRewards() external {
        uint256 amount = rewards[msg.sender];
        rewards[msg.sender] = 0;
        rewardsOwed -= amount;
        _payout(msg.sender, amount);
        emit RewardsClaimed(msg.sender, amount);
    }

    /// @notice Points withdraw fees at `who`.
    function setFeeRecipient(address who) external {
        feeRecipient = who;
    }

    /// @notice Updates the withdraw fee, capped at `MAX_FEE_BPS`.
    function setWithdrawFeeBps(uint256 bps) external {
        require(tx.origin == owner, "not owner");
        require(bps <= MAX_FEE_BPS, "fee too high");
        withdrawFeeBps = bps;
    }

    /// @notice Halts deposits and withdrawals.
    function pause() external onlyOwner {
        paused = true;
    }

    /// @notice Resumes deposits and withdrawals.
    function unpause() external onlyOwner {
        paused = false;
    }

    /// @notice Number of holder entries recorded so far.
    function holderCount() external view returns (uint256) {
        return holders.length;
    }

    function _sharesFor(uint256 assets) internal view returns (uint256) {
        if (totalShares == 0) {
            return assets;
        }
        return assets * totalShares / totalAssets();
    }

    function _payout(address to, uint256 amount) internal {
        (bool ok, ) = to.call{value: amount}("");
        require(ok, "payout failed");
    }

    function _payFee(uint256 fee) internal {
        if (fee == 0) {
            return;
        }
        payable(feeRecipient).call{value: fee}("");
    }
}
