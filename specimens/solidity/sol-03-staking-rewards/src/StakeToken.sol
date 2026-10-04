// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface ITokenReceiver {
    function onTokenReceived(address from, uint256 amount) external;
}

/// @title StakeToken
/// @notice Minimal ERC20-style token that reports failure as `false`, with an
///         opt-in receive hook for contract recipients.
contract StakeToken {
    string public constant name = "Stake Token";
    string public constant symbol = "STK";
    uint8 public constant decimals = 18;

    uint256 public totalSupply;

    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;
    mapping(address => bool) public receiveHookEnabled;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(
        address indexed owner, address indexed spender, uint256 value
    );

    /// @notice Mints `amount` tokens to the caller.
    function mint(uint256 amount) external {
        totalSupply += amount;
        balanceOf[msg.sender] += amount;
        emit Transfer(address(0), msg.sender, amount);
    }

    /// @notice Opts the caller in or out of receive notifications.
    function setReceiveHook(bool enabled) external {
        receiveHookEnabled[msg.sender] = enabled;
    }

    /// @notice Moves `amount` tokens to `to`; false when underfunded.
    function transfer(address to, uint256 amount) external returns (bool) {
        return _move(msg.sender, to, amount);
    }

    /// @notice Grants `spender` an allowance of `amount` tokens.
    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        emit Approval(msg.sender, spender, amount);
        return true;
    }

    /// @notice Moves `amount` from `from` to `to`, spending allowance.
    function transferFrom(
        address from,
        address to,
        uint256 amount
    ) external returns (bool) {
        if (allowance[from][msg.sender] < amount) {
            return false;
        }
        allowance[from][msg.sender] -= amount;
        return _move(from, to, amount);
    }

    function _move(
        address from,
        address to,
        uint256 amount
    ) internal returns (bool) {
        if (balanceOf[from] < amount) {
            return false;
        }
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
        emit Transfer(from, to, amount);
        _notifyReceiver(from, to, amount);
        return true;
    }

    /// @dev Delivers the opt-in ERC777-style receive notification.
    function _notifyReceiver(
        address from,
        address to,
        uint256 amount
    ) internal {
        if (receiveHookEnabled[to] && to.code.length > 0) {
            ITokenReceiver(to).onTokenReceived(from, amount);
        }
    }
}
