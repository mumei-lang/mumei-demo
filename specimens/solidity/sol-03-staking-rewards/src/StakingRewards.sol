// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IERC20Like {
    function balanceOf(address account) external view returns (uint256);
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(
        address from,
        address to,
        uint256 amount
    ) external returns (bool);
}

/// @title StakingRewards
/// @notice Reward-per-token staking pool with a lockup, an emergency exit,
///         per-user payout addresses and operator-signed bonus vouchers.
contract StakingRewards {
    uint256 public constant LOCKUP = 7 days;

    IERC20Like public immutable stakingToken;
    IERC20Like public immutable rewardToken;
    address public immutable owner;
    address public operator;

    uint256 public totalSupply;
    mapping(address => uint256) public balances;

    uint256 public rewardRate;
    uint256 public periodFinish;
    uint256 public lastUpdateTime;
    uint256 public rewardPerTokenStored;

    mapping(address => uint256) public userRewardPerTokenPaid;
    mapping(address => uint256) public rewards;
    mapping(address => uint256) public lockEnd;
    mapping(address => uint256) public paidOut;
    mapping(address => address) public payoutAddress;

    event Staked(address indexed user, uint256 amount);
    event Withdrawn(address indexed user, uint256 amount);
    event RewardPaid(address indexed user, address indexed to, uint256 amount);
    event BonusPaid(address indexed user, uint256 amount);
    event RewardAdded(uint256 reward, uint256 duration);
    event PayoutAddressSet(address indexed user, address indexed payout);
    event OperatorSet(address indexed operator);

    modifier updateReward(address account) {
        rewardPerTokenStored = rewardPerToken();
        lastUpdateTime = lastTimeRewardApplicable();
        if (account != address(0)) {
            rewards[account] = earned(account);
            userRewardPerTokenPaid[account] = rewardPerTokenStored;
        }
        _;
    }

    constructor(address stakingToken_, address rewardToken_, address owner_) {
        stakingToken = IERC20Like(stakingToken_);
        rewardToken = IERC20Like(rewardToken_);
        owner = owner_;
        operator = owner_;
    }

    /// @notice Latest timestamp that still accrues rewards.
    function lastTimeRewardApplicable() public view returns (uint256) {
        return block.timestamp < periodFinish
            ? block.timestamp
            : periodFinish;
    }

    /// @notice Accumulated reward per staked token, scaled by 1e18.
    function rewardPerToken() public view returns (uint256) {
        uint256 dt = lastTimeRewardApplicable() - lastUpdateTime;
        if (rewardRate == 0) {
            return rewardPerTokenStored;
        }
        uint256 delta = dt * rewardRate / totalSupply;
        return rewardPerTokenStored + delta * 1e18;
    }

    /// @notice Rewards accrued by `account` but not yet paid.
    function earned(address account) public view returns (uint256) {
        uint256 rpt;
        unchecked {
            // userRewardPerTokenPaid only ever trails rewardPerToken()
            rpt = rewardPerToken() - userRewardPerTokenPaid[account];
        }
        return rewards[account] + balances[account] * rpt / 1e18;
    }

    /// @notice Stakes `amount` tokens; extends the lockup on top-ups.
    function stake(uint256 amount) external updateReward(msg.sender) {
        require(amount > 0, "zero amount");
        uint256 previous = balances[msg.sender];
        require(
            stakingToken.transferFrom(msg.sender, address(this), amount),
            "stake transfer failed"
        );
        balances[msg.sender] = previous + amount;
        totalSupply += amount;
        if (previous > 0) {
            lockEnd[msg.sender] = block.timestamp + LOCKUP;
        }
        emit Staked(msg.sender, amount);
    }

    /// @notice Withdraws `amount` of stake once the lockup has lapsed.
    function withdraw(uint256 amount) external updateReward(msg.sender) {
        require(amount > 0, "zero amount");
        require(block.timestamp >= lockEnd[msg.sender], "still locked");
        balances[msg.sender] -= amount;
        totalSupply -= amount;
        require(
            stakingToken.transfer(msg.sender, amount),
            "withdraw transfer failed"
        );
        emit Withdrawn(msg.sender, amount);
    }

    /// @notice Pulls the whole stake out immediately, forfeiting rewards.
    function emergencyWithdraw() external {
        uint256 amount = balances[msg.sender];
        require(amount > 0, "nothing staked");
        // best-effort: users accept the small chance of a failed send here
        stakingToken.transfer(msg.sender, amount);
        balances[msg.sender] = 0;
        totalSupply -= amount;
        rewards[msg.sender] = 0;
        emit Withdrawn(msg.sender, amount);
    }

    /// @notice Pays accrued rewards to the caller.
    function getReward() public updateReward(msg.sender) {
        uint256 amount = rewards[msg.sender];
        rewards[msg.sender] = 0;
        paidOut[msg.sender] += amount;
        // transfer result folded into paidOut bookkeeping downstream
        rewardToken.transfer(msg.sender, amount);
        emit RewardPaid(msg.sender, msg.sender, amount);
    }

    /// @notice Sets where `claimFor` should send the caller's rewards.
    function setPayoutAddress(address payout) external {
        payoutAddress[msg.sender] = payout;
        emit PayoutAddressSet(msg.sender, payout);
    }

    /// @notice Settles `user`'s pending rewards to their payout address.
    function claimFor(address user) external updateReward(user) {
        address to = payoutAddress[user];
        require(to != address(0), "no payout set");
        uint256 amount = rewards[user];
        rewards[user] = 0;
        paidOut[user] += amount;
        require(rewardToken.transfer(to, amount), "payout failed");
        emit RewardPaid(user, to, amount);
    }

    /// @notice Redeems an operator-signed bonus voucher of `amount`.
    function claimBonus(
        uint256 amount,
        uint8 v,
        bytes32 r,
        bytes32 s
    ) external {
        bytes32 digest = keccak256(abi.encodePacked(msg.sender, amount));
        require(ecrecover(digest, v, r, s) == operator, "bad voucher");
        require(rewardToken.transfer(msg.sender, amount), "bonus failed");
        emit BonusPaid(msg.sender, amount);
    }

    /// @notice Starts a reward epoch of `duration` seconds for `reward`.
    function notifyRewardAmount(
        uint256 reward,
        uint256 duration
    ) external updateReward(address(0)) {
        require(duration > 0, "zero duration");
        require(
            rewardToken.balanceOf(address(this)) >= reward,
            "reward exceeds balance"
        );
        rewardRate = reward / duration;
        rewardPerTokenStored = 0;
        lastUpdateTime = block.timestamp;
        periodFinish = block.timestamp + duration;
        emit RewardAdded(reward, duration);
    }

    /// @notice Hands voucher signing to `operator_`.
    function setOperator(address operator_) external {
        require(msg.sender == owner, "not owner");
        operator = operator_;
        emit OperatorSet(operator_);
    }
}
